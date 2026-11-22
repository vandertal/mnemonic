import { apiFetch, apiJson, jsonBody } from './client'
import { parseSse, type SseMessage } from './sse'
import type { ChatEvent, Chunk, FlashcardSet, Source, StoredMessage, ToolEvent } from './types'

/** One SSE message -> a typed chat event. Pure (no I/O), so it is unit-tested directly.
 *  Unknown event names give null: a newer server may add events an older SPA ignores. */
export function toChatEvent(msg: SseMessage): ChatEvent | null {
  switch (msg.event) {
    case 'message':
      return { type: 'token', text: String(JSON.parse(msg.data)) }
    case 'sources':
      return { type: 'sources', sources: JSON.parse(msg.data) as Source[] }
    case 'tool':
      return { type: 'tool', tool: JSON.parse(msg.data) as ToolEvent }
    case 'done':
      return { type: 'done', messageId: (JSON.parse(msg.data) as { message_id: number | null }).message_id }
    case 'error':
      return { type: 'error', message: String(JSON.parse(msg.data)) }
    default:
      return null
  }
}

/** POST /chat and yield typed events. Aborting `signal` cancels the request and ends the stream. */
export async function* streamChat(
  sessionId: string,
  message: string,
  signal: AbortSignal,
): AsyncGenerator<ChatEvent> {
  const res = await apiFetch('/chat', {
    ...jsonBody({ session_id: sessionId, message }),
    signal,
  })
  if (!res.body) throw new Error('The response has no body')

  for await (const msg of parseSse(res.body)) {
    const event = toChatEvent(msg)
    if (event) yield event
  }
}

export const fetchHistory = (sessionId: string, signal?: AbortSignal) =>
  apiJson<StoredMessage[]>(`/sessions/${sessionId}/messages`, { signal })

export const fetchChunk = (id: number) =>
  apiJson<Chunk>(`/chunks/${id}`)

export const createFlashcards = (sessionId: string, messageId: number) =>
  apiJson<FlashcardSet>('/flashcards', jsonBody({ session_id: sessionId, message_id: messageId }))
