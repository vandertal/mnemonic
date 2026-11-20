import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchHistory, streamChat } from '@/api/chat'
import { isAbort } from '@/api/errors'
import type { Source, ToolEvent } from '@/api/types'
import { describeError, toastError } from '@/lib/errors'

export interface ChatMessage {
  key: string
  role: 'user' | 'assistant'
  content: string
  sources: Source[]
  tools: ToolEvent[]
  status: 'streaming' | 'done' | 'stopped' | 'error'
  error?: string
}

type History = 'loading' | 'ready' | 'error'

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [history, setHistory] = useState<History>('loading')
  const [busy, setBusy] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  // The state starts as 'loading'; callers that retry set it themselves.
  const loadHistory = useCallback((signal?: AbortSignal) => {
    fetchHistory(signal).then(
      (stored) => {
        setMessages(
          stored.map((m) => ({
            key: `db-${m.id}`,
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
        setHistory('error')
        toastError(e)
      },
    )
  }, [])

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
      for await (const ev of streamChat(question, ctrl.signal)) {
        if (ev.type === 'token') patch((m) => ({ ...m, content: m.content + ev.text }))
        else if (ev.type === 'sources') patch((m) => ({ ...m, sources: ev.sources }))
        else if (ev.type === 'tool') patch((m) => ({ ...m, tools: [...m.tools, ev.tool] }))
        else if (ev.type === 'done') patch((m) => ({ ...m, status: 'done' }))
        else patch((m) => ({ ...m, status: 'error', error: ev.message }))
      }
      patch((m) => (m.status === 'streaming' ? { ...m, status: 'done' } : m))
    } catch (e) {
      if (isAbort(e)) patch((m) => ({ ...m, status: 'stopped' }))
      else {
        patch((m) => ({ ...m, status: 'error', error: describeError(e) }))
        toastError(e)
      }
    } finally {
      abortRef.current = null
      setBusy(false)
    }
  }, [])

  const reloadHistory = useCallback(() => {
    setHistory('loading')
    loadHistory()
  }, [loadHistory])

  const stop = useCallback(() => abortRef.current?.abort(), [])

  return { messages, history, busy, send, stop, reloadHistory }
}
