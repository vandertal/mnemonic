import type { Flashcard } from '@/api/types'
import { readJson, removeJson, writeJson } from '@/lib/storage'

export interface Deck {
  id: string // `${sessionId}:${messageId}`: making cards twice from one answer replaces the deck
  question: string // the user question the answer belonged to
  createdAt: number
  cards: Flashcard[]
}

// Decks live only in this browser (localStorage), one list per user id. The server stores no decks.
const key = (userId: string) => `decks.${userId}`

const isDeck = (x: unknown): x is Deck => {
  const d = x as Deck
  return !!d && typeof d.id === 'string' && typeof d.question === 'string' && Array.isArray(d.cards)
}

export function loadDecks(userId: string): Deck[] {
  const stored = readJson<unknown>(key(userId), [])
  return (Array.isArray(stored) ? stored.filter(isDeck) : []).sort((a, b) => b.createdAt - a.createdAt)
}

export function saveDeck(userId: string, deck: Deck): void {
  writeJson(key(userId), [deck, ...loadDecks(userId).filter((d) => d.id !== deck.id)])
}

export function deleteDeck(userId: string, id: string): void {
  writeJson(key(userId), loadDecks(userId).filter((d) => d.id !== id))
}

/** Account deletion: this user's decks go with the account. */
export const removeDecks = (userId: string) => removeJson(key(userId))
