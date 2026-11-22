import { BookOpen } from 'lucide-react'
import type { ReactNode } from 'react'
import { LanguageSwitcher } from '@/components/language-switcher'
import { OfflineBanner } from '@/components/offline-banner'
import { ThemeToggle } from '@/components/theme-toggle'
import { Card } from '@/components/ui/card'

/** Shared frame of /login and /register: centered card, language + theme switches, offline banner. */
export function AuthLayout({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <div className="relative grid min-h-dvh place-items-center bg-background px-4 py-16">
      <div className="absolute inset-x-0 top-0">
        <OfflineBanner />
      </div>
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
