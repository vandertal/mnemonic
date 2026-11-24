import { describe, expect, it } from 'vitest'
import { toChatEvent } from '@/api/chat'
import type { ChatEvent } from '@/api/types'
import { applyChatEvent, llmErrorKey } from './events'
import type { ChatMessage } from './use-chat'

const blank: ChatMessage = {
  key: 'a',
  role: 'assistant',
  content: '',
  sources: [],
  tools: [],
  status: 'streaming',
  live: true,
}
const t = (key: string) => key
const run = (events: ChatEvent[]) => events.reduce((m, ev) => applyChatEvent(m, ev, t), blank)

describe('the server retry protocol (reset)', () => {
  it('discards the partial text, so the retried answer is not shown twice', () => {
    const m = run([
      { type: 'token', text: 'Half an ans' },
      { type: 'reset' },
      { type: 'token', text: 'The full answer.' },
      { type: 'done', messageId: 7 },
    ])
    expect(m.content).toBe('The full answer.')
    expect(m.status).toBe('done')
    expect(m.messageId).toBe(7)
  })

  it('also drops the tool notes and sources of the failed attempt', () => {
    const tool = { name: 'calculator', args: {}, result: '4' }
    const m = run([{ type: 'tool', tool }, { type: 'token', text: 'x' }, { type: 'reset' }])
    expect(m).toMatchObject({ content: '', tools: [], sources: [], status: 'streaming' })
  })

  it('a final failure after a reset keeps the error state and shows the localized sentence', () => {
    const m = run([{ type: 'token', text: 'a' }, { type: 'reset' }, { type: 'error', message: 'English', kind: 'quota' }])
    expect(m.status).toBe('error')
    expect(m.error).toBe('errors.llmQuota')
  })
})

describe('error classes', () => {
  it.each([
    ['quota', 'errors.llmQuota'],
    ['overloaded', 'errors.llmOverloaded'],
    ['blocked', 'errors.llmBlocked'],
    ['timeout', 'errors.llmTimeout'],
    ['busy', 'errors.busy'],
    ['other', 'errors.llm'],
    [undefined, 'errors.llm'],
    ['something-new', 'errors.llm'],
  ])('%s -> %s', (kind, key) => {
    expect(llmErrorKey(kind)).toBe(key)
  })
})

describe('toChatEvent for the new events', () => {
  it('reset, refusal and a structured error', () => {
    expect(toChatEvent({ event: 'reset', data: '""' })).toEqual({ type: 'reset' })
    expect(toChatEvent({ event: 'refusal', data: '{"reason":"non_english"}' })).toEqual({ type: 'refusal', reason: 'non_english' })
    expect(toChatEvent({ event: 'error', data: '{"kind":"quota","message":"m"}' })).toEqual({ type: 'error', message: 'm', kind: 'quota' })
  })

  it('an old bare-string error still works', () => {
    expect(toChatEvent({ event: 'error', data: '"boom"' })).toEqual({ type: 'error', message: 'boom' })
  })

  it('the non-English refusal marks the message so the UI can show the hint', () => {
    const m = run([{ type: 'token', text: "I don't know." }, { type: 'refusal', reason: 'non_english' }, { type: 'done', messageId: 2 }])
    expect(m.refusalReason).toBe('non_english')
  })
})
