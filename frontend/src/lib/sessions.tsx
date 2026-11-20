import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { readJson, readStored, writeJson, writeStored } from './storage'

export interface ChatSession {
  id: string
  title: string // '' until the first question is sent
  updatedAt: number
}

interface SessionsValue {
  sessions: ChatSession[] // newest activity first
  activeId: string
  newChat: () => void
  select: (id: string) => void
  remove: (id: string) => void
  /** Called when a question is sent: names an untitled session and bumps it to the top. */
  touch: (id: string, question: string) => void
}

const SessionsContext = createContext<SessionsValue | null>(null)
const TITLE_MAX = 40

const titleFrom = (question: string) => {
  const flat = question.replace(/\s+/g, ' ').trim()
  return flat.length > TITLE_MAX ? `${flat.slice(0, TITLE_MAX).trimEnd()}…` : flat
}

const sortByActivity = (list: ChatSession[]) => [...list].sort((a, b) => b.updatedAt - a.updatedAt)
const fresh = (): ChatSession => ({ id: crypto.randomUUID(), title: '', updatedAt: Date.now() })

function isSession(x: unknown): x is ChatSession {
  const s = x as ChatSession
  return !!s && typeof s.id === 'string' && typeof s.title === 'string' && typeof s.updatedAt === 'number'
}

function load(): { sessions: ChatSession[]; activeId: string } {
  const stored = readJson<unknown>('sessions', [])
  let sessions = Array.isArray(stored) ? stored.filter(isSession) : []
  // The pre-M2 single session id is adopted, so old history is not lost.
  const legacy = readStored('sessionId')
  if (legacy && !sessions.some((s) => s.id === legacy)) {
    sessions = [...sessions, { id: legacy, title: '', updatedAt: 0 }]
  }
  if (!sessions.length) sessions = [fresh()]
  sessions = sortByActivity(sessions)
  const activeId = sessions.some((s) => s.id === legacy) ? legacy! : sessions[0].id
  return { sessions, activeId }
}

export function SessionsProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState(load)

  // Persist inside the updater functions' results, never in an effect: one write per change.
  const commit = useCallback((next: { sessions: ChatSession[]; activeId: string }) => {
    writeJson('sessions', next.sessions)
    writeStored('sessionId', next.activeId)
    setState(next)
  }, [])

  const newChat = useCallback(() => {
    // An empty chat is already a "new chat": do not pile up blank entries.
    const blank = state.sessions.find((s) => s.id === state.activeId && !s.title)
    if (blank) return
    const created = fresh()
    commit({ sessions: sortByActivity([created, ...state.sessions]), activeId: created.id })
  }, [state, commit])

  const select = useCallback(
    (id: string) => {
      if (id !== state.activeId && state.sessions.some((s) => s.id === id)) commit({ ...state, activeId: id })
    },
    [state, commit],
  )

  const remove = useCallback(
    (id: string) => {
      let sessions = state.sessions.filter((s) => s.id !== id)
      let activeId = state.activeId
      if (id === activeId) {
        // Deleting the open chat opens a new one, as the brief says.
        const created = fresh()
        sessions = [created, ...sessions]
        activeId = created.id
      }
      commit({ sessions: sortByActivity(sessions), activeId })
    },
    [state, commit],
  )

  const touch = useCallback(
    (id: string, question: string) => {
      const sessions = state.sessions.map((s) =>
        s.id === id ? { ...s, title: s.title || titleFrom(question), updatedAt: Date.now() } : s,
      )
      commit({ ...state, sessions: sortByActivity(sessions) })
    },
    [state, commit],
  )

  const value = useMemo(
    () => ({ sessions: state.sessions, activeId: state.activeId, newChat, select, remove, touch }),
    [state, newChat, select, remove, touch],
  )
  return <SessionsContext.Provider value={value}>{children}</SessionsContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSessions() {
  const ctx = useContext(SessionsContext)
  if (!ctx) throw new Error('useSessions must be used inside SessionsProvider')
  return ctx
}
