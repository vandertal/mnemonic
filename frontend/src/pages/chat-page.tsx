import { useQueryClient } from '@tanstack/react-query'
import { BookOpen, SearchX } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/card'
import { Composer } from '@/features/chat/composer'
import { MessageView } from '@/features/chat/message'
import { useChat } from '@/features/chat/use-chat'
import { EmptyState as NoticeState } from '@/components/empty-state'
import {
  SESSIONS_KEY,
  useCreateSession,
  useForgetSession,
  useSessions,
} from '@/features/sessions/use-sessions'

function EmptyState({ onPick }: { onPick: (q: string) => void }) {
  const { t } = useTranslation()
  const suggestions = t('chat.suggestions', { returnObjects: true }) as string[]
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 py-10 text-center">
      <div className="grid size-12 place-items-center rounded-xl bg-accent-soft text-accent">
        <BookOpen className="size-6" />
      </div>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{t('chat.title')}</h1>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">{t('chat.subtitle')}</p>
      </div>
      <div className="flex max-w-xl flex-wrap justify-center gap-2">
        {suggestions.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => onPick(s)}
            className="cursor-pointer rounded-full border bg-card px-3.5 py-1.5 text-sm shadow-sm transition-colors hover:bg-muted"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}

/** /chat/:sessionId shows that chat; plain /chat opens the latest one (or makes the first). */
export default function ChatPage() {
  const { sessionId } = useParams()
  // Remounted per session (key=): switching chats drops all local state and aborts a running stream.
  return sessionId ? <ChatView key={sessionId} sessionId={sessionId} /> : <ChatHome />
}

function ChatHome() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { sessions, isPending, isError, refetch } = useSessions()
  const create = useCreateSession()
  const asked = useRef(false) // StrictMode runs effects twice: one blank chat, not two
  const latest = sessions[0]

  const makeFirst = () => {
    asked.current = true
    create.mutate(undefined, { onSuccess: (c) => navigate(`/chat/${c.id}`, { replace: true }) })
  }
  useEffect(() => {
    if (!isPending && !isError && !latest && !asked.current) makeFirst()
  })

  if (latest) return <Navigate to={`/chat/${latest.id}`} replace />
  if (isError || create.isError) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
        <p className="text-sm text-muted-foreground">{t('chat.sessionsFailed')}</p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            create.reset()
            asked.current = false
            void refetch()
          }}
        >
          {t('chat.retry')}
        </Button>
      </div>
    )
  }
  return (
    <div className="mx-auto w-full max-w-3xl space-y-3 px-4 py-6" role="status" aria-label={t('chat.loadingHistory')}>
      <Skeleton className="ml-auto h-10 w-1/2" />
      <Skeleton className="h-4 w-11/12" />
    </div>
  )
}

function ChatView({ sessionId }: { sessionId: string }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const forget = useForgetSession()
  const { messages, history, busy, send, stop, reloadHistory } = useChat(sessionId, {
    // The server sets the title when the first question is saved: refresh the sidebar.
    onAnswered: () => void qc.invalidateQueries({ queryKey: SESSIONS_KEY }),
    onNotFound: () => forget(sessionId),
  })
  const scroller = useRef<HTMLDivElement>(null)
  const stick = useRef(true) // follow the stream only while the reader is at the bottom

  useEffect(() => {
    const el = scroller.current
    if (el && stick.current) el.scrollTo({ top: el.scrollHeight })
  }, [messages])

  const onScroll = () => {
    const el = scroller.current
    if (el) stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120
  }

  const onSend = (text: string) => {
    stick.current = true
    void send(text)
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div ref={scroller} onScroll={onScroll} className="flex-1 overflow-y-auto">
        <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col gap-6 px-4 py-6">
          {history === 'loading' ? (
            <div className="space-y-3" role="status" aria-label={t('chat.loadingHistory')}>
              <Skeleton className="ml-auto h-10 w-1/2" />
              <Skeleton className="h-4 w-11/12" />
              <Skeleton className="h-4 w-3/4" />
            </div>
          ) : history === 'notFound' ? (
            <NoticeState
              icon={SearchX}
              title={t('chat.notFoundTitle')}
              text={t('chat.notFoundText')}
              action={<Button onClick={() => navigate('/chat', { replace: true })}>{t('chat.openLatest')}</Button>}
            />
          ) : history === 'error' ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
              <p className="text-sm text-muted-foreground">{t('chat.historyFailed')}</p>
              <Button variant="outline" size="sm" onClick={reloadHistory}>
                {t('chat.retry')}
              </Button>
            </div>
          ) : messages.length === 0 ? (
            <EmptyState onPick={onSend} />
          ) : (
            messages.map((m, i) => (
              <MessageView
                key={m.key}
                message={m}
                sessionId={sessionId}
                question={messages.slice(0, i).findLast((p) => p.role === 'user')?.content ?? ''}
              />
            ))
          )}
        </div>
      </div>
      <div className="px-4 pb-4">
        <div className="mx-auto w-full max-w-3xl">
          <Composer busy={busy} onSend={onSend} onStop={stop} />
        </div>
      </div>
    </div>
  )
}
