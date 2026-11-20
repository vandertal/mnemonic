import type { TFunction } from 'i18next'
import { toast } from 'sonner'
import i18n from '@/i18n'
import { ApiError, AuthError, NetworkError, isAbort } from '@/api/errors'

/** A human sentence for any error. Server `detail` is shown only for statuses where it is meant for users. */
export function describeError(e: unknown, t: TFunction = i18n.t): string {
  if (e instanceof AuthError) return t('errors.auth')
  if (e instanceof NetworkError) return t('errors.network')
  if (e instanceof ApiError) {
    if (e.status === 429 || e.status === 503) return t('errors.busy')
    if (e.status >= 500 && e.status !== 502) return t('errors.server')
    return e.message || t('errors.generic')
  }
  return t('errors.generic')
}

export function toastError(e: unknown) {
  if (isAbort(e)) return
  toast.error(describeError(e))
}
