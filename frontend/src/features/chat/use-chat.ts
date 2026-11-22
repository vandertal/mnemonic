import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchHistory, streamChat } from '@/api/chat'
import { NotFoundError, isAbort } from '@/api/errors'
import type { Source, ToolEvent } from '@/api/types'
import { describeError, toastError } from '@/lib/errors'

export interface ChatMessage {
  key: string
  /** Server id of a saved assistant answer; needed to make flashcards from it. */
  messageId?: number
  role: 'user' | 'assistant'
  content: string
  sources: Source[]
  tools: ToolEvent[]
  status: 'streaming' | 'done' | 'stopped' | 'error'
  error?: string
}

type History = 'loading' | 'ready' | 'error' | 'notFound'

interface Callbacks {
  /** After every answer attempt (finished, failed or stopped): the server may have set the title. */
  onAnswered: () => void
  /** The server says this session does not exist (deleted elsewhere, or not ours). */
  onNotFound: () => void
}

/** One chat session. The page remounts it per session (key=), so no state leaks between chats. */
export function useChat(sessionId: string, callbacks: Callbacks) {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [history, setHistory] = useState<History>('loading')
  const [busy, setBusy] = useState(false)
  const abortRef = useRef<AbortController | null>(null)
  const cb = useRef(callbacks)
  useEffect(() => {
    cb.current = callbacks
  })

  // The state starts as 'loading'; callers that retry set it themselves.
  const loadHistory = useCallback((signal?: AbortSignal) => {
    fetchHistory(sessionId, signal).then(
      (stored) => {
        setMessages(
          stored.map((m) => ({
            key: `db-${m.id}`,
            messageId: m.role === 'assistant' ? m.id : undefined,
            role: m.role,
            content: m.content,
            sources: m.sources ?? [],
            tools: [],
            status: 'done',
          })),
        )
        setHistory('ready')
      },
      (e) => {
        if (isAbort(e)) return
        if (e instanceof NotFoundError) {
          setHistory('notFound')
          cb.current.onNotFound()
          return
        }
        setHistory('error')
        toastError(e)
      },
    )
  }, [sessionId])

  useEffect(() => {
    const ctrl = new AbortController()
    loadHistory(ctrl.signal)
    return () => ctrl.abort()
  }, [loadHistory])

  // Leaving the page must cancel a running stream (and so close the connection).
  useEffect(() => () => abortRef.current?.abort(), [])

  const send = useCallback(async (text: string) => {
    const question = text.trim()
    if (!question || abortRef.current) return
    const ctrl = new AbortController()
    abortRef.current = ctrl
    setBusy(true)

    const id = crypto.randomUUID()
    const assistantKey = `a-${id}`
    const patch = (fn: (m: ChatMessage) => ChatMessage) =>
      setMessages((all) => all.map((m) => (m.key === assistantKey ? fn(m) : m)))

    setMessages((all) => [
      ...all,
      { key: `u-${id}`, role: 'user', content: question, sources: [], tools: [], status: 'done' },
      { key: assistantKey, role: 'assistant', content: '', sources: [], tools: [], status: 'streaming' },
    ])

    try {
      for await (const ev of streamChat(sessionId, question, ctrl.signal)) {
        if (ev.type === 'token') patch((m) => ({ ...m, content: m.content + ev.text }))
        else if (ev.type === 'sources') patch((m) => ({ ...m, sources: ev.sources }))
        else if (ev.type === 'tool') patch((m) => ({ ...m, tools: [...m.tools, ev.tool] }))
        else if (ev.type === 'done') patch((m) => ({ ...m, status: 'done', messageId: ev.messageId ?? undefined }))
        else patch((m) => ({ ...m, status: 'error', error: ev.message }))
      }
      patch((m) => (m.status === 'streaming' ? { ...m, status: 'done' } : m))
    } catch (e) {
      if (isAbort(e)) patch((m) => ({ ...m, status: 'stopped' }))
      else if (e instanceof NotFoundError) {
        setHistory('notFound')
        cb.current.onNotFound()
      } else {
        patch((m) => ({ ...m, status: 'error', error: describeError(e) }))
        toastError(e)
      }
    } finally {
      abortRef.current = null
      setBusy(false)
      cb.current.onAnswered()
    }
  }, [sessionId])

  const reloadHistory = useCallback(() => {
    setHistory('loading')
    loadHistory()
  }, [loadHistory])

  const stop = useCallback(() => abortRef.current?.abort(), [])

  return { messages, history, busy, send, stop, reloadHistory }
}
