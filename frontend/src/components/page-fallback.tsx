import { useTranslation } from 'react-i18next'
import { Skeleton } from '@/components/ui/card'

/** Shown while a lazy page chunk downloads. Same outer box as the pages (title + content blocks), so nothing jumps. */
export function PageFallback({ inShell }: { inShell?: boolean }) {
  const { t } = useTranslation()
  return (
    <div
      role="status"
      aria-label={t('common.loading')}
      className={inShell ? 'flex-1 overflow-y-auto px-4 py-6' : 'grid min-h-dvh place-items-center px-4'}
    >
      <div className={inShell ? 'mx-auto max-w-3xl space-y-4' : 'w-full max-w-sm space-y-4'}>
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-4 w-64 max-w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    </div>
  )
}
