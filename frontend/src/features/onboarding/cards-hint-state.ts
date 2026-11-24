import type { ChatMessage } from '@/features/chat/use-chat'
import { readJson, writeJson } from '@/lib/storage'

// One subtle hint after the first cited answer: "you can turn this into flashcards". Dismissed once,
// remembered per user id (two accounts in one browser each see it once).
const key = (userId: string) => `onboarding.cardsHint.${userId}`

export const isCardsHintDismissed = (userId: string): boolean => readJson<unknown>(key(userId), false) === true

export const dismissCardsHint = (userId: string): void => writeJson(key(userId), true)

/**
 * Only on the newest answer, only if it was produced right now (not loaded from history), finished,
 * saved on the server (so "Make flashcards" works) and has sources: that is when the button exists.
 */
export function shouldShowCardsHint(message: ChatMessage, isLast: boolean, dismissed: boolean): boolean {
  return (
    !dismissed &&
    isLast &&
    message.role === 'assistant' &&
    message.live === true &&
    message.status === 'done' &&
    message.messageId !== undefined &&
    message.sources.length > 0
  )
}
