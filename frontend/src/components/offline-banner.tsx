import { WifiOff } from 'lucide-react'
import { useSyncExternalStore } from 'react'
import { useTranslation } from 'react-i18next'

function subscribe(onChange: () => void) {
  window.addEventListener('online', onChange)
  window.addEventListener('offline', onChange)
  return () => {
    window.removeEventListener('online', onChange)
    window.removeEventListener('offline', onChange)
  }
}

const useOnline = () => useSyncExternalStore(subscribe, () => navigator.onLine, () => true)

/** Shown while the browser reports no connection. TanStack Query refetches on reconnect by itself. */
export function OfflineBanner() {
  const { t } = useTranslation()
  if (useOnline()) return null
  return (
    <div
      role="status"
      className="flex items-center justify-center gap-2 border-b border-warning-border bg-warning-soft px-3 py-1.5 text-sm"
    >
      <WifiOff className="size-4 shrink-0" />
      {t('offline.banner')}
    </div>
  )
}
