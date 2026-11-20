import { BookOpen, FileText, Layers, Menu, MessageSquare, PanelLeftClose, PanelLeftOpen, Settings } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { NavLink, Outlet } from 'react-router-dom'
import { LanguageSwitcher } from '@/components/language-switcher'
import { ThemeToggle } from '@/components/theme-toggle'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
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

function SidebarBody({ collapsed, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const { t } = useTranslation()
  return (
    <>
      <Brand collapsed={collapsed} />
      <nav className="flex flex-1 flex-col gap-1 px-2 py-2">
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
        <main className="flex min-h-0 flex-1 flex-col">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
