import {
  BookOpen,
  FileText,
  Layers,
  Menu,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Settings,
  Trash2,
} from 'lucide-react'
import { Suspense, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { PageFallback } from '@/components/page-fallback'
import { OfflineBanner } from '@/components/offline-banner'
import { LanguageSwitcher } from '@/components/language-switcher'
import { ThemeToggle } from '@/components/theme-toggle'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { useSessions } from '@/lib/sessions'
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

function SessionList({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { sessions, activeId, select, remove } = useSessions()
  return (
    <ul className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto px-2 pb-2" aria-label={t('chat.sessions')}>
      {sessions.map((s) => (
        <li key={s.id} className="group relative">
          <button
            type="button"
            onClick={() => {
              select(s.id)
              navigate('/chat')
              onNavigate?.()
            }}
            aria-current={s.id === activeId ? 'true' : undefined}
            className={cn(
              'flex h-8 w-full cursor-pointer items-center rounded-md pr-8 pl-3 text-left text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground',
              s.id === activeId && 'bg-accent-soft font-medium text-foreground',
            )}
          >
            <span className="truncate">{s.title || t('chat.newChat')}</span>
          </button>
          <button
            type="button"
            onClick={() => remove(s.id)}
            aria-label={t('chat.deleteSession', { title: s.title || t('chat.newChat') })}
            className="absolute top-1 right-1 grid size-6 cursor-pointer place-items-center rounded text-muted-foreground hover:bg-background hover:text-destructive focus-visible:opacity-100 md:opacity-0 md:group-hover:opacity-100"
          >
            <Trash2 className="size-3.5" />
          </button>
        </li>
      ))}
    </ul>
  )
}

function SidebarBody({ collapsed, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { newChat } = useSessions()
  const startChat = () => {
    newChat()
    navigate('/chat')
    onNavigate?.()
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
