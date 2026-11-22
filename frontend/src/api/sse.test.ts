import { afterEach, describe, expect, it, vi } from 'vitest'

import * as storage from '@/lib/storage'
import { streamChat, toChatEvent } from './chat'
import { setAuthFailureHandler } from './client'
import { AuthError } from './errors'
import { parseSse, type SseMessage } from './sse'
import type { ChatEvent } from './types'

// No localStorage in Node: replace the token helpers and watch clearToken. vi.mock is hoisted
// above the imports, so `storage` is already the mock.
vi.mock('@/lib/storage', () => ({
  getToken: vi.fn(() => 'token-123'),
  clearToken: vi.fn(),
}))

/** A body that delivers exactly these pieces, one per read(): the way the network splits bytes. */
function streamOf(...pieces: (string | Uint8Array)[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder()
  return new ReadableStream({
    start(controller) {
      for (const p of pieces) controller.enqueue(typeof p === 'string' ? enc.encode(p) : p)
      controller.close()
    },
  })
}

async function collect(body: ReadableStream<Uint8Array>): Promise<SseMessage[]> {
  const out: SseMessage[] = []
  for await (const msg of parseSse(body)) out.push(msg)
  return out
}

describe('parseSse', () => {
  it('joins a token split across network chunks', async () => {
    expect(await collect(streamOf('da', 'ta: "Hel', 'lo"\n', '\n'))).toEqual([
      { event: 'message', data: '"Hello"' },
    ])
  })

  it('joins a UTF-8 character split between two chunks', async () => {
    const bytes = new TextEncoder().encode('data: "привіт"\n\n')
    expect(await collect(streamOf(bytes.slice(0, 8), bytes.slice(8)))).toEqual([
      { event: 'message', data: '"привіт"' },
    ])
  })

  it('joins multi-line data with \\n', async () => {
    expect(await collect(streamOf('data: line one\ndata: line two\n\n'))).toEqual([
      { event: 'message', data: 'line one\nline two' },
    ])
  })

  it('accepts CRLF line endings', async () => {
    expect(await collect(streamOf('event: done\r\ndata: {}\r\n\r\n'))).toEqual([
      { event: 'done', data: '{}' },
    ])
  })

  it('does not end an event early when the \\r and \\n of one CRLF arrive in different chunks', async () => {
    expect(await collect(streamOf('data: a\r', '\ndata: b\r\n\r\n'))).toEqual([
      { event: 'message', data: 'a\nb' },
    ])
  })

  it('yields a trailing event that has no closing blank line', async () => {
    expect(await collect(streamOf('data: "a"\n\n', 'event: done\ndata: {"message_id": 3}'))).toEqual([
      { event: 'message', data: '"a"' },
      { event: 'done', data: '{"message_id": 3}' },
    ])
  })

  it('skips comments (keep-alive) and events without data', async () => {
    expect(await collect(streamOf(': ping\n\nevent: sources\n\ndata: "x"\n\n'))).toEqual([
      { event: 'message', data: '"x"' },
    ])
  })
})

describe('toChatEvent', () => {
  it.each<[SseMessage, ChatEvent]>([
    [{ event: 'message', data: '"Hi"' }, { type: 'token', text: 'Hi' }],
    [
      { event: 'sources', data: '[{"id": 1, "file_path": "a.md", "heading": "A", "similarity": 0.9}]' },
      { type: 'sources', sources: [{ id: 1, file_path: 'a.md', heading: 'A', similarity: 0.9 }] },
    ],
    [{ event: 'done', data: '{"message_id": 42}' }, { type: 'done', messageId: 42 }],
    [{ event: 'done', data: '{"message_id": null}' }, { type: 'done', messageId: null }],
    [
      { event: 'tool', data: '{"name": "calculator", "args": {"expression": "2+2"}, "result": "4"}' },
      { type: 'tool', tool: { name: 'calculator', args: { expression: '2+2' }, result: '4' } },
    ],
    [{ event: 'error', data: '"LLM timeout"' }, { type: 'error', message: 'LLM timeout' }],
  ])('maps %o', (msg, expected) => {
    expect(toChatEvent(msg)).toEqual(expected)
  })

  it('ignores unknown events, even when their data is not JSON', () => {
    expect(toChatEvent({ event: 'future-thing', data: 'not json' })).toBeNull()
  })
})

describe('streamChat', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('yields typed events from the response body, unknown ones dropped', async () => {
    const body = streamOf(
      'event: sources\ndata: []\n\n',
      'data: "Hel',
      'lo"\n\nevent: whatever\ndata: 1\n\n',
      'event: done\ndata: {"message_id": 7}\n\n',
    )
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => new Response(body, { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const events: ChatEvent[] = []
    for await (const e of streamChat('s1', 'hi', new AbortController().signal)) events.push(e)

    expect(events).toEqual([
      { type: 'sources', sources: [] },
      { type: 'token', text: 'Hello' },
      { type: 'done', messageId: 7 },
    ])
    const init = fetchMock.mock.calls[0][1]
    expect(new Headers(init?.headers).get('Authorization')).toBe('Bearer token-123')
  })

  it('a 401 on the stream request clears the token and calls onAuthFailure', async () => {
    const onAuthFailure = vi.fn()
    setAuthFailureHandler(onAuthFailure)
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ detail: 'Not authenticated' }, { status: 401 })),
    )

    const events: ChatEvent[] = []
    const run = async () => {
      for await (const e of streamChat('s1', 'hi', new AbortController().signal)) events.push(e)
    }

    await expect(run()).rejects.toBeInstanceOf(AuthError)
    expect(events).toEqual([])
    expect(storage.clearToken).toHaveBeenCalledOnce()
    expect(onAuthFailure).toHaveBeenCalledOnce()
  })
})
