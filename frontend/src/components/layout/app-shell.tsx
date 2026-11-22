import {
  BookOpen,
  FileText,
  Layers,
  Menu,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Plus,
  Settings,
  Trash2,
} from 'lucide-react'
import { Suspense, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { NavLink, Outlet, useMatch, useNavigate } from 'react-router-dom'
import { PageFallback } from '@/components/page-fallback'
import { OfflineBanner } from '@/components/offline-banner'
import { LanguageSwitcher } from '@/components/language-switcher'
import { ThemeToggle } from '@/components/theme-toggle'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import {
  DEFAULT_TITLE,
  useCreateSession,
  useDeleteSession,
  useRenameSession,
  useSessions,
} from '@/features/sessions/use-sessions'
import { readStored, writeStored } from '@/lib/storage'
import { cn } from '@/lib/utils'

const NAV = [
  { to: '/chat', icon: MessageSquare, key: 'nav.chat' },
  { to: '/documents', icon: FileText, key: 'nav.documents' },
  { to: '/flashcards', icon: Layers, key: 'nav.flashcards' },
  { to: '/settings', icon: Settings, key: 'nav.settings' },
]

function Brand({ collapsed }: { collapsed?: boolean }) {
  const { t } = useTranslation()
  return (
    <div className="flex h-14 items-center gap-2.5 px-4">
      <div className="grid size-8 shrink-0 place-items-center rounded-md bg-accent text-accent-foreground">
        <BookOpen className="size-4" />
      </div>
      {!collapsed && <span className="text-[15px] font-semibold tracking-tight">{t('app.name')}</span>}
    </div>
  )
}

/** The server's placeholder title is shown translated; real titles are shown as they are. */
const displayTitle = (title: string, t: (k: string) => string) => (title === DEFAULT_TITLE ? t('chat.newChat') : title)

function SessionRow({ id, title, active, onNavigate }: { id: string; title: string; active: boolean; onNavigate?: () => void }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const rename = useRenameSession()
  const remove = useDeleteSession()
  const [editing, setEditing] = useState(false)
  const shown = displayTitle(title, t)

  const commit = (value: string) => {
    setEditing(false)
    const next = value.trim().slice(0, 100)
    if (next && next !== shown) rename.mutate({ id, title: next })
  }
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') commit(e.currentTarget.value)
    else if (e.key === 'Escape') setEditing(false)
  }

  if (editing) {
    return (
      <li className="px-1">
        <input
          autoFocus
          defaultValue={shown}
          maxLength={100}
          aria-label={t('chat.renameSession')}
          onKeyDown={onKey}
          onBlur={(e) => commit(e.currentTarget.value)}
          className="h-8 w-full rounded-md border border-input bg-card px-2 text-sm"
        />
      </li>
    )
  }
  return (
    <li className="group relative">
      <button
        type="button"
        onClick={() => {
          navigate(`/chat/${id}`)
          onNavigate?.()
        }}
        onDoubleClick={() => setEditing(true)}
        aria-current={active ? 'true' : undefined}
        className={cn(
          'flex h-8 w-full cursor-pointer items-center rounded-md pr-14 pl-3 text-left text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground',
          active && 'bg-accent-soft font-medium text-foreground',
        )}
      >
        <span className="truncate">{shown}</span>
      </button>
      <div className="absolute top-1 right-1 flex focus-within:opacity-100 md:opacity-0 md:group-hover:opacity-100">
        <button
          type="button"
          onClick={() => setEditing(true)}
          aria-label={t('chat.renameSessionNamed', { title: shown })}
          className="grid size-6 cursor-pointer place-items-center rounded text-muted-foreground hover:bg-background hover:text-foreground"
        >
          <Pencil className="size-3.5" />
        </button>
        <button
          type="button"
          onClick={() => {
            remove.mutate(id)
            if (active) navigate('/chat')
          }}
          aria-label={t('chat.deleteSession', { title: shown })}
          className="grid size-6 cursor-pointer place-items-center rounded text-muted-foreground hover:bg-background hover:text-destructive"
        >
          <Trash2 className="size-3.5" />
        </button>
      </div>
    </li>
  )
}

function SessionList({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation()
  const activeId = useMatch('/chat/:sessionId')?.params.sessionId
  const { sessions, isPending, isError, refetch, hasNextPage, fetchNextPage, isFetchingNextPage } = useSessions()

  if (isPending) {
    return (
      <div className="space-y-1.5 px-3 py-1" role="status" aria-label={t('common.loading')}>
        <Skeleton className="h-6 w-full" />
        <Skeleton className="h-6 w-5/6" />
        <Skeleton className="h-6 w-2/3" />
      </div>
    )
  }
  if (isError) {
    return (
      <div className="flex flex-col items-start gap-2 px-3 py-1 text-sm text-muted-foreground">
        {t('chat.sessionsFailed')}
        <Button variant="outline" size="sm" onClick={() => void refetch()}>
          {t('chat.retry')}
        </Button>
      </div>
    )
  }
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-2 pb-2">
      <ul className="flex flex-col gap-0.5" aria-label={t('chat.sessions')}>
        {sessions.map((s) => (
          <SessionRow key={s.id} id={s.id} title={s.title} active={s.id === activeId} onNavigate={onNavigate} />
        ))}
      </ul>
      {hasNextPage && (
        <Button variant="ghost" size="sm" className="mt-1" disabled={isFetchingNextPage} onClick={() => void fetchNextPage()}>
          {isFetchingNextPage ? t('common.loading') : t('chat.loadMore')}
        </Button>
      )}
    </div>
  )
}

function SidebarBody({ collapsed, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const activeId = useMatch('/chat/:sessionId')?.params.sessionId
  const { sessions } = useSessions()
  const create = useCreateSession()
  const startChat = () => {
    onNavigate?.()
    // An untouched chat is already a "new chat": open it instead of piling up blank ones.
    const blank = sessions.find((s) => s.id === activeId && s.title === DEFAULT_TITLE)
    if (blank) return navigate(`/chat/${blank.id}`)
    create.mutate(undefined, { onSuccess: (created) => navigate(`/chat/${created.id}`) })
  }
  return (
    <>
      <Brand collapsed={collapsed} />
      <div className={cn('px-2', collapsed && 'flex justify-center')}>
        <Button
          variant="outline"
          size={collapsed ? 'icon' : 'default'}
          className={cn(!collapsed && 'w-full justify-start')}
          onClick={startChat}
          disabled={create.isPending}
          title={collapsed ? t('chat.newChat') : undefined}
          aria-label={t('chat.newChat')}
        >
          <Plus className="size-4" />
          {!collapsed && t('chat.newChat')}
        </Button>
      </div>
      <nav className="flex flex-col gap-1 px-2 py-2">
        {NAV.map(({ to, icon: Icon, key }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onNavigate}
            title={collapsed ? t(key) : undefined}
            className={({ isActive }) =>
              cn(
                'flex h-9 items-center gap-3 rounded-md px-3 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground',
                collapsed && 'justify-center px-0',
                isActive && 'bg-accent-soft text-foreground',
              )
            }
          >
            <Icon className="size-4 shrink-0" />
            {!collapsed && t(key)}
          </NavLink>
        ))}
      </nav>
      {collapsed ? <div className="flex-1" /> : <SessionList onNavigate={onNavigate} />}
      {!collapsed && (
        <div className="flex items-center justify-between gap-2 border-t p-3">
          <LanguageSwitcher />
          <ThemeToggle />
        </div>
      )}
    </>
  )
}

export function AppShell() {
  const { t } = useTranslation()
  const [collapsed, setCollapsed] = useState(() => readStored('sidebar') === '1')
  const [drawer, setDrawer] = useState(false)

  const toggle = () =>
    setCollapsed((c) => {
      writeStored('sidebar', c ? '0' : '1')
      return !c
    })

  return (
    <div className="flex h-dvh bg-background">
      {/* Desktop sidebar */}
      <aside
        className={cn(
          'hidden shrink-0 flex-col border-r bg-sidebar transition-[width] duration-200 md:flex',
          collapsed ? 'w-16' : 'w-64',
        )}
      >
        <SidebarBody collapsed={collapsed} />
        <div className={cn('flex border-t p-2', collapsed ? 'justify-center' : 'justify-end')}>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={toggle}
            aria-label={collapsed ? t('nav.expand') : t('nav.collapse')}
          >
            {collapsed ? <PanelLeftOpen className="size-4" /> : <PanelLeftClose className="size-4" />}
          </Button>
        </div>
      </aside>

      {/* Mobile drawer */}
      <Dialog open={drawer} onOpenChange={setDrawer}>
        <DialogContent side="left" className="flex flex-col bg-sidebar p-0">
          <DialogTitle className="sr-only">{t('app.name')}</DialogTitle>
          <DialogDescription className="sr-only">{t('app.tagline')}</DialogDescription>
          <SidebarBody onNavigate={() => setDrawer(false)} />
        </DialogContent>
      </Dialog>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b px-3 md:hidden">
          <Button variant="ghost" size="icon" onClick={() => setDrawer(true)} aria-label={t('nav.openMenu')}>
            <Menu className="size-5" />
          </Button>
          <span className="font-semibold tracking-tight">{t('app.name')}</span>
        </header>
        <OfflineBanner />
        <main className="flex min-h-0 flex-1 flex-col">
          <Suspense fallback={<PageFallback inShell />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  )
}
