import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { LanguageSwitcher } from '@/components/language-switcher'
import { ThemeToggle } from '@/components/theme-toggle'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useAuth } from '@/lib/auth'

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <span className="text-sm font-medium">{label}</span>
      {children}
    </div>
  )
}

export default function SettingsPage() {
  const { t } = useTranslation()
  const { signOut } = useAuth()
  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      <div className="mx-auto max-w-3xl space-y-6">
        <h1 className="text-xl font-semibold tracking-tight">{t('settings.title')}</h1>
        <Card className="divide-y px-5">
          <h2 className="pt-4 pb-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">
            {t('settings.appearance')}
          </h2>
          <Row label={t('settings.theme')}>
            <ThemeToggle />
          </Row>
          <Row label={t('settings.language')}>
            <LanguageSwitcher />
          </Row>
        </Card>
        <Card className="p-5">
          <h2 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{t('settings.access')}</h2>
          <p className="mt-2 text-sm text-muted-foreground">{t('settings.accessText')}</p>
          <Button variant="destructive" className="mt-4" onClick={signOut}>
            {t('settings.signOut')}
          </Button>
        </Card>
      </div>
    </div>
  )
}
