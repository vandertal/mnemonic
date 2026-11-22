import { apiFetch, apiJson, jsonBody } from './client'
import type { ChatSession, SessionPage } from './types'

export const PAGE_SIZE = 20

export const fetchSessions = (offset: number) =>
  apiJson<SessionPage>(`/sessions?limit=${PAGE_SIZE}&offset=${offset}`)

/** The server makes the id (and the "New chat" title); the client never invents one. */
export const createSession = () => apiJson<ChatSession>('/sessions', jsonBody({}))

export const renameSession = (id: string, title: string) =>
  apiJson<ChatSession>(`/sessions/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })

export async function deleteSession(id: string): Promise<void> {
  await apiFetch(`/sessions/${id}`, { method: 'DELETE' })
}
