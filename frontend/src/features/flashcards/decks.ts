import type { Flashcard } from '@/api/types'
import { getOrCreateId, readJson, writeJson } from '@/lib/storage'

export interface Deck {
  id: string // `${sessionId}:${messageId}`: making cards twice from one answer replaces the deck
  question: string // the user question the answer belonged to
  createdAt: number
  cards: Flashcard[]
}

// Decks live only in this browser (localStorage), one list per owner id. The server stores no decks.
const key = () => `decks.${getOrCreateId('ownerId')}`

const isDeck = (x: unknown): x is Deck => {
  const d = x as Deck
  return !!d && typeof d.id === 'string' && typeof d.question === 'string' && Array.isArray(d.cards)
}

export function loadDecks(): Deck[] {
  const stored = readJson<unknown>(key(), [])
  return (Array.isArray(stored) ? stored.filter(isDeck) : []).sort((a, b) => b.createdAt - a.createdAt)
}

export function saveDeck(deck: Deck): void {
  writeJson(key(), [deck, ...loadDecks().filter((d) => d.id !== deck.id)])
}

export function deleteDeck(id: string): void {
  writeJson(key(), loadDecks().filter((d) => d.id !== id))
}
