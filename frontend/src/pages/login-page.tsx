import { zodResolver } from '@hookform/resolvers/zod'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { toast } from 'sonner'
import { z } from 'zod'
import { AuthLayout, Field } from '@/components/auth-layout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/lib/auth'
import { authErrorKey, describeError } from '@/lib/errors'
import { AuthError } from '@/api/errors'
import { fromPath } from '@/lib/redirect'

// Messages are i18n keys, translated at render, so they follow the language switcher.
const schema = z.object({
  email: z.string().trim().min(1, 'auth.emailRequired').pipe(z.email('auth.emailInvalid')),
  password: z.string().min(8, 'auth.passwordShort').max(128, 'auth.passwordLong'),
})
type Values = z.infer<typeof schema>

export default function LoginPage() {
  const { t } = useTranslation()
  const { status, login } = useAuth()
  const location = useLocation()
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: '', password: '' } })

  // Signed in (also right after a successful submit): go where the visitor wanted to go.
  if (status !== 'anonymous') return <Navigate to={fromPath(location.state)} replace />

  const onSubmit = async ({ email, password }: Values) => {
    try {
      await login(email, password)
    } catch (e) {
      const key = authErrorKey(e)
      if (e instanceof AuthError) setError('root', { message: key })
      else toast.error(key ? t(key) : describeError(e, t))
    }
  }

  return (
    <AuthLayout title={t('auth.loginTitle')} description={t('auth.loginText')}>
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
            autoComplete="current-password"
            aria-invalid={!!errors.password}
            aria-describedby={errors.password ? 'password-error' : undefined}
            {...register('password')}
          />
        </Field>
        {errors.root?.message && (
          <p role="alert" className="text-sm text-destructive">
            {t(errors.root.message)}
          </p>
        )}
        <Button type="submit" className="w-full" disabled={isSubmitting}>
          {isSubmitting ? t('auth.signingIn') : t('auth.signIn')}
        </Button>
      </form>
      <p className="mt-5 text-center text-sm text-muted-foreground">
        {t('auth.noAccount')}{' '}
        <Link to="/register" state={location.state} className="font-medium text-accent hover:underline">
          {t('auth.signUp')}
        </Link>
      </p>
    </AuthLayout>
  )
}
