import { BookOpen } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { LanguageSwitcher } from '@/components/language-switcher'
import { OfflineBanner } from '@/components/offline-banner'
import { ColdStartBanner } from '@/components/cold-start-banner'
import { ThemeToggle } from '@/components/theme-toggle'
import { Card } from '@/components/ui/card'

/** Shared frame of /login and /register: centered card, language + theme switches, offline banner. */
export function AuthLayout({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  const { t } = useTranslation()
  return (
    <div className="relative grid min-h-dvh place-items-center bg-background px-4 py-16">
      <div className="absolute inset-x-0 top-0">
        <OfflineBanner />
        <ColdStartBanner />
      </div>
      {/* The way back to the landing page. Logged-in visitors never see this screen (they are redirected into the app). */}
      <Link
        to="/"
        className="absolute top-4 left-4 flex items-center gap-2 rounded-md px-1 py-1 text-sm font-medium text-foreground hover:text-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        <span className="grid size-7 place-items-center rounded-md bg-accent text-accent-foreground">
          <BookOpen className="size-4" aria-hidden="true" />
        </span>
        <span>Mnemonic</span>
        <span className="sr-only">: {t('auth.backHome')}</span>
      </Link>
      <div className="absolute top-4 right-4 flex gap-2">
        <LanguageSwitcher />
        <ThemeToggle />
      </div>
      <Card className="w-full max-w-sm p-6">
        <div className="mb-5 grid size-10 place-items-center rounded-md bg-accent text-accent-foreground">
          <BookOpen className="size-5" />
        </div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">{description}</p>
        {children}
      </Card>
    </div>
  )
}

export function Field({
  id,
  label,
  error,
  children,
}: {
  id: string
  label: string
  error?: string
  children: ReactNode
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      {children}
      {error && (
        <p id={`${id}-error`} role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}
