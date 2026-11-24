import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ChatMessage } from '@/features/chat/use-chat'

// An in-memory stand-in for localStorage, keyed like the real helpers.
const store = new Map<string, unknown>()
vi.mock('@/lib/storage', () => ({
  readJson: <T>(key: string, fallback: T): T => (store.has(key) ? (store.get(key) as T) : fallback),
  writeJson: (key: string, value: unknown) => void store.set(key, value),
}))

import { dismissCardsHint, isCardsHintDismissed, shouldShowCardsHint } from './cards-hint-state'

const answer = (over: Partial<ChatMessage> = {}): ChatMessage => ({
  key: 'a-1',
  role: 'assistant',
  content: 'Use CORSMiddleware [1].',
  sources: [{ id: 1, file_path: 'tutorial/cors.md', heading: 'CORS', similarity: 0.9 }],
  tools: [],
  status: 'done',
  messageId: 7,
  live: true,
  ...over,
})

beforeEach(() => store.clear())

describe('shouldShowCardsHint', () => {
  it('shows under the newest, finished, cited, saved answer made in this session', () => {
    expect(shouldShowCardsHint(answer(), true, false)).toBe(true)
  })

  it.each([
    ['it was dismissed before', answer(), true, true],
    ['it is not the newest message', answer(), false, false],
    ['the answer came from history, not from this session', answer({ live: false }), true, false],
    ['it is still streaming', answer({ status: 'streaming' }), true, false],
    ['it failed', answer({ status: 'error' }), true, false],
    ['there are no sources (an honest "I don\'t know")', answer({ sources: [] }), true, false],
    ['it was not saved, so "Make flashcards" does not exist', answer({ messageId: undefined }), true, false],
    ['it is the user\'s own message', answer({ role: 'user' }), true, false],
  ])('hides when %s', (_why, message, isLast, dismissed) => {
    expect(shouldShowCardsHint(message, isLast, dismissed)).toBe(false)
  })
})

describe('dismissal is remembered per user id', () => {
  it('starts not dismissed, then stays dismissed for that user only', () => {
    expect(isCardsHintDismissed('alice')).toBe(false)
    dismissCardsHint('alice')
    expect(isCardsHintDismissed('alice')).toBe(true)
    expect(isCardsHintDismissed('bob')).toBe(false)
  })
})
