import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { toast } from 'sonner'
import { z } from 'zod'
import { ConflictError, ForbiddenError, RateLimitError } from '@/api/errors'
import { AuthLayout, Field } from '@/components/auth-layout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/lib/auth'
import { authErrorKey, describeError } from '@/lib/errors'
import { fromPath } from '@/lib/redirect'
import { useCooldown } from '@/lib/use-cooldown'

const schema = z.object({
  email: z.string().trim().min(1, 'auth.emailRequired').pipe(z.email('auth.emailInvalid')),
  password: z.string().min(8, 'auth.passwordShort').max(128, 'auth.passwordLong'),
  invite: z.string().trim().max(200, 'auth.inviteLong').optional(),
})
type Values = z.infer<typeof schema>

export default function RegisterPage() {
  const { t } = useTranslation()
  const { status, register: signUp } = useAuth()
  const location = useLocation()
  const cooldown = useCooldown()
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: '', password: '', invite: '' } })

  if (status !== 'anonymous') return <Navigate to={fromPath(location.state)} replace />

  const onSubmit = async ({ email, password, invite }: Values) => {
    try {
      await signUp(email, password, invite || undefined)
    } catch (e) {
      const key = authErrorKey(e)
      if (e instanceof ConflictError) setError('email', { message: key })
      else if (e instanceof ForbiddenError) setError('invite', { message: key })
      else if (e instanceof RateLimitError) cooldown.start(e.retryAfter ?? 60)
      else toast.error(key ? t(key) : describeError(e, t))
    }
  }

  return (
    <AuthLayout title={t('auth.registerTitle')} description={t('auth.registerText')}>
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="mt-5 space-y-4">
        <Field id="email" label={t('auth.email')} error={errors.email?.message && t(errors.email.message)}>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            autoFocus
            aria-invalid={!!errors.email}
            aria-describedby={errors.email ? 'email-error' : undefined}
            {...register('email')}
          />
        </Field>
        <Field id="password" label={t('auth.password')} error={errors.password?.message && t(errors.password.message)}>
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            aria-invalid={!!errors.password}
            aria-describedby={errors.password ? 'password-error' : undefined}
            {...register('password')}
          />
        </Field>
        <Field id="invite" label={t('auth.invite')} error={errors.invite?.message && t(errors.invite.message)}>
          <Input
            id="invite"
            type="password"
            autoComplete="off"
            placeholder={t('auth.invitePlaceholder')}
            aria-invalid={!!errors.invite}
            aria-describedby={errors.invite ? 'invite-error' : undefined}
            {...register('invite')}
          />
        </Field>
        {cooldown.left > 0 && (
          <p role="alert" className="text-sm text-destructive">
            {t('auth.tooManyWait', { seconds: cooldown.left })}
          </p>
        )}
        <Button type="submit" className="w-full" disabled={isSubmitting || cooldown.left > 0}>
          {isSubmitting
            ? t('auth.signingUp')
            : cooldown.left > 0
              ? t('auth.tryIn', { seconds: cooldown.left })
              : t('auth.signUpButton')}
        </Button>
      </form>
      <p className="mt-5 text-center text-sm text-muted-foreground">
        {t('auth.haveAccount')}{' '}
        <Link to="/login" state={location.state} className="font-medium text-accent hover:underline">
          {t('auth.signIn')}
        </Link>
      </p>
    </AuthLayout>
  )
}
