import { Moon } from 'lucide-react'
import { useEffect, useState, useSyncExternalStore } from 'react'
import { useTranslation } from 'react-i18next'
import { getWakingSince, subscribeCold } from '@/lib/cold-start'

/** "Server is waking up" with a running timer, while the API has not answered for more than 4 s. */
export function ColdStartBanner() {
  const { t } = useTranslation()
  const since = useSyncExternalStore(subscribeCold, getWakingSince, () => null)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (since === null) return
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [since])

  if (since === null) return null
  const seconds = Math.max(0, Math.floor((now - since) / 1000))
  return (
    <div
      role="status"
      className="flex items-center justify-center gap-2 border-b border-warning-border bg-warning-soft px-3 py-1.5 text-center text-sm"
    >
      <Moon className="size-4 shrink-0" aria-hidden="true" />
      <span>{t('coldStart.banner')}</span>
      <span className="tabular-nums text-muted-foreground">{t('coldStart.elapsed', { seconds })}</span>
    </div>
  )
}
