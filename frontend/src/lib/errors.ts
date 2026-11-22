import type { TFunction } from 'i18next'
import { toast } from 'sonner'
import i18n from '@/i18n'
import {
  ApiError,
  AuthError,
  ConflictError,
  ForbiddenError,
  NetworkError,
  NotFoundError,
  RateLimitError,
  isAbort,
} from '@/api/errors'

/** A human sentence for any error. Auth-related statuses never show the server's `detail`. */
export function describeError(e: unknown, t: TFunction = i18n.t): string {
  if (e instanceof AuthError) return t('errors.auth')
  if (e instanceof NetworkError) return t('errors.network')
  if (e instanceof ForbiddenError) return t('errors.forbidden')
  if (e instanceof ConflictError) return t('errors.conflict')
  if (e instanceof NotFoundError) return t('errors.notFound')
  if (e instanceof RateLimitError) return t('errors.busy')
  if (e instanceof ApiError) {
    if (e.status === 503) return t('errors.busy')
    if (e.status >= 500 && e.status !== 502) return t('errors.server')
    return e.message || t('errors.generic')
  }
  return t('errors.generic')
}

/** i18n key of the message a login/register form shows for each typed error (`undefined`: not one of them). */
export function authErrorKey(e: unknown): string | undefined {
  if (e instanceof AuthError) return 'auth.wrongCredentials'
  if (e instanceof ForbiddenError) return 'auth.badInvite'
  if (e instanceof ConflictError) return 'auth.emailTaken'
  if (e instanceof RateLimitError) return 'auth.tooMany'
  return undefined
}

export function toastError(e: unknown) {
  if (isAbort(e)) return
  toast.error(describeError(e))
}
