import { useQueryClient } from '@tanstack/react-query'
import { WifiOff } from 'lucide-react'
import { useSyncExternalStore } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'

function subscribe(onChange: () => void) {
  window.addEventListener('online', onChange)
  window.addEventListener('offline', onChange)
  return () => {
    window.removeEventListener('online', onChange)
    window.removeEventListener('offline', onChange)
  }
}

const useOnline = () => useSyncExternalStore(subscribe, () => navigator.onLine, () => true)

/**
 * Shown while the browser reports no connection. TanStack Query refetches on reconnect by itself;
 * "Retry" is for the impatient (and for a flaky `navigator.onLine`): it refetches everything now.
 */
export function OfflineBanner() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  if (useOnline()) return null

  const retry = async () => {
    await qc.refetchQueries({ type: 'active' })
    if (!navigator.onLine) toast.error(t('errors.network'))
  }
  return (
    <div
      role="status"
      className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 border-b border-warning-border bg-warning-soft px-3 py-1.5 text-sm"
    >
      <span className="flex items-center gap-2">
        <WifiOff className="size-4 shrink-0" aria-hidden="true" />
        {t('offline.banner')}
      </span>
      <Button variant="outline" size="sm" className="h-7" onClick={() => void retry()}>
        {t('offline.retry')}
      </Button>
    </div>
  )
}
