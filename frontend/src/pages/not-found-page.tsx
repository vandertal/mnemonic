import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'

export default function NotFoundPage() {
  const { t } = useTranslation()
  return (
    <div className="grid min-h-dvh place-items-center bg-background px-4 text-center">
      <div>
        <p className="text-5xl font-semibold tracking-tight text-accent">404</p>
        <h1 className="mt-3 text-xl font-semibold">{t('notFound.title')}</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">{t('notFound.text')}</p>
        <Button asChild className="mt-6">
          <Link to="/chat">{t('notFound.home')}</Link>
        </Button>
      </div>
    </div>
  )
}
