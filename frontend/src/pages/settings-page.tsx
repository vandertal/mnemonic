import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { LanguageSwitcher } from '@/components/language-switcher'
import { ThemeToggle } from '@/components/theme-toggle'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { useAuth } from '@/lib/auth'
import { toastError } from '@/lib/errors'

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
  const { user, logout, deleteAccount } = useAuth()
  const [confirm, setConfirm] = useState(false)
  const [deleting, setDeleting] = useState(false)

  const onDelete = async () => {
    setDeleting(true)
    try {
      await deleteAccount() // clears the token and the caches; RequireAuth then sends us to /register
      toast.success(t('settings.deleted'))
    } catch (e) {
      setDeleting(false)
      setConfirm(false)
      toastError(e)
    }
  }

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
          <h2 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{t('settings.account')}</h2>
          <p className="mt-2 text-sm text-muted-foreground">{t('settings.signedInAs')}</p>
          <p className="text-sm font-medium break-all">{user?.email}</p>
          <p className="mt-3 text-sm text-muted-foreground">{t('settings.accountText')}</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Button variant="outline" onClick={logout}>
              {t('settings.signOut')}
            </Button>
            <Button variant="destructive" onClick={() => setConfirm(true)}>
              {t('settings.deleteAccount')}
            </Button>
          </div>
        </Card>
      </div>
      <ConfirmDialog
        open={confirm}
        title={t('settings.deleteTitle')}
        description={t('settings.deleteText')}
        confirmLabel={deleting ? t('settings.deleting') : t('settings.deleteConfirm')}
        onCancel={() => !deleting && setConfirm(false)}
        onConfirm={() => void onDelete()}
      />
    </div>
  )
}
