import { afterEach, describe, expect, it, vi } from 'vitest'

// No localStorage or DOM in Node: stub what the API client and the error texts import.
vi.mock('@/lib/storage', () => ({ getToken: vi.fn(() => 'token-123'), clearToken: vi.fn() }))
vi.mock('@/i18n', () => ({ default: { t: (k: string) => k } }))

import { describeError } from '@/lib/errors'
import * as storage from '@/lib/storage'
import { streamChat } from './chat'
import { apiFetch, setAuthFailureHandler } from './client'
import {
  ApiError,
  RateLimitError,
  StreamInterruptedError,
  ValidationError,
  errorForStatus,
  parseRetryAfter,
} from './errors'

// A translator that shows the key and the parameters, so the tests see what the user would get.
const t = ((key: string, opts?: Record<string, unknown>) => (opts ? `${key} ${JSON.stringify(opts)}` : key)) as never

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('parseRetryAfter', () => {
  it.each([
    ['30', 30],
    [' 5 ', 5],
    ['0', null],
    ['-3', null],
    ['abc', null],
    ['Wed, 21 Oct 2026 07:28:00 GMT', null],
    ['99999', null],
    [null, null],
  ])('%j -> %j', (input, expected) => {
    expect(parseRetryAfter(input)).toBe(expected)
  })
})

describe('429 and 422 from the API client', () => {
  it('a 429 carries the Retry-After seconds, and a friendly text with the wait', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ detail: 'busy' }, { status: 429, headers: { 'Retry-After': '42' } })),
    )
    const err = await apiFetch('/chat').catch((e) => e)
    expect(err).toBeInstanceOf(RateLimitError)
    expect(err.retryAfter).toBe(42)
    expect(describeError(err, t)).toBe('errors.busyWait {"seconds":42}')
  })

  it('a 429 without the header still gets the plain friendly text', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({ detail: 'busy' }, { status: 429 })))
    const err = await apiFetch('/chat').catch((e) => e)
    expect(err.retryAfter).toBeNull()
    expect(describeError(err, t)).toBe('errors.busy')
  })

  it('a 422 list becomes a ValidationError, shown in our language, never as raw pydantic text', async () => {
    const detail = [{ type: 'string_too_long', loc: ['body', 'message'], msg: 'String should have at most 2000 characters' }]
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({ detail }, { status: 422 })))
    const err = await apiFetch('/chat').catch((e) => e)
    expect(err).toBeInstanceOf(ValidationError)
    expect(describeError(err, t)).toBe('errors.tooLong')
  })

  it('a blank question (our own validator message) maps to the "type a question" text', () => {
    const e = errorForStatus(422, 'Value error, The question is empty', {
      problems: [{ type: 'value_error', loc: ['body', 'message'], msg: 'Value error, The question is empty' }],
    })
    expect(describeError(e, t)).toBe('errors.emptyInput')
  })

  it('an unknown 422 gets the generic invalid-input text', () => {
    const e = errorForStatus(422, 'x', { problems: [{ type: 'weird', loc: [], msg: 'x' }] })
    expect(describeError(e, t)).toBe('errors.invalidInput')
  })

  it('a 422 with a plain-string detail (an upload problem) keeps its readable sentence', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({ detail: 'The file has no text' }, { status: 422 })))
    const err = await apiFetch('/documents', { method: 'POST' }).catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err).not.toBeInstanceOf(ValidationError)
    expect(describeError(err, t)).toBe('The file has no text')
  })

  it('a 401 (expired token) clears the token and tells the auth provider, once', async () => {
    const onAuthFailure = vi.fn()
    setAuthFailureHandler(onAuthFailure)
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({ detail: 'Invalid or expired token' }, { status: 401 })))
    await apiFetch('/sessions').catch(() => {})
    expect(storage.clearToken).toHaveBeenCalledTimes(1)
    expect(onAuthFailure).toHaveBeenCalledTimes(1)
  })

  it('a wrong password on login (skipAuthFailure) does not log anyone out', async () => {
    const onAuthFailure = vi.fn()
    setAuthFailureHandler(onAuthFailure)
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({ detail: 'x' }, { status: 401 })))
    await apiFetch('/auth/login', { method: 'POST', skipAuthFailure: true }).catch(() => {})
    expect(onAuthFailure).not.toHaveBeenCalled()
  })

  it('a dead network is a NetworkError with the "check your connection" text', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('Failed to fetch'))))
    const err = await apiFetch('/sessions').catch((e) => e)
    expect(describeError(err, t)).toBe('errors.network')
  })
})

describe('an answer that is cut off mid-stream', () => {
  const enc = new TextEncoder()
  const collect = async () => {
    const out: string[] = []
    for await (const e of streamChat('s', 'q', new AbortController().signal)) out.push(e.type)
    return out
  }

  it('ending without done/error throws StreamInterruptedError after the partial tokens', async () => {
    const body = new ReadableStream({
      start(c) {
        c.enqueue(enc.encode('data: "Hel"\n\n'))
        c.close()
      },
    })
    vi.stubGlobal('fetch', vi.fn(async () => new Response(body)))
    const seen: string[] = []
    const run = async () => {
      for await (const e of streamChat('s', 'q', new AbortController().signal)) seen.push(e.type)
    }
    await expect(run()).rejects.toBeInstanceOf(StreamInterruptedError)
    expect(seen).toEqual(['token']) // what already arrived is still delivered
  })

  it('a connection that breaks while reading is the same error', async () => {
    const body = new ReadableStream({
      start(c) {
        c.enqueue(enc.encode('data: "Hel"\n\n'))
        c.error(new TypeError('network error'))
      },
    })
    vi.stubGlobal('fetch', vi.fn(async () => new Response(body)))
    await expect(collect()).rejects.toBeInstanceOf(StreamInterruptedError)
    expect(describeError(new StreamInterruptedError(), t)).toBe('errors.streamCut')
  })

  it('an error event from the server is a normal ending (the UI shows its own sentence)', async () => {
    const body = new ReadableStream({
      start(c) {
        c.enqueue(enc.encode('data: "Hel"\n\nevent: error\ndata: "boom"\n\n'))
        c.close()
      },
    })
    vi.stubGlobal('fetch', vi.fn(async () => new Response(body)))
    expect(await collect()).toEqual(['token', 'error'])
  })
})
