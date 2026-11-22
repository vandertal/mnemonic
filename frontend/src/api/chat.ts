import { apiFetch, apiJson, jsonBody } from './client'
import { parseSse } from './sse'
import type { ChatEvent, Chunk, FlashcardSet, Source, StoredMessage, ToolEvent } from './types'

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
    const data: unknown = JSON.parse(msg.data)
    switch (msg.event) {
      case 'message':
        yield { type: 'token', text: String(data) }
        break
      case 'sources':
        yield { type: 'sources', sources: data as Source[] }
        break
      case 'tool':
        yield { type: 'tool', tool: data as ToolEvent }
        break
      case 'done':
        yield { type: 'done', messageId: (data as { message_id: number | null }).message_id }
        break
      case 'error':
        yield { type: 'error', message: String(data) }
        break
    }
  }
}

export const fetchHistory = (sessionId: string, signal?: AbortSignal) =>
  apiJson<StoredMessage[]>(`/sessions/${sessionId}/messages`, { signal })

export const fetchChunk = (id: number) =>
  apiJson<Chunk>(`/chunks/${id}`)

export const createFlashcards = (sessionId: string, messageId: number) =>
  apiJson<FlashcardSet>('/flashcards', jsonBody({ session_id: sessionId, message_id: messageId }))
