import { zodResolver } from '@hookform/resolvers/zod'
import { BookOpen } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { Navigate, useNavigate } from 'react-router-dom'
import { z } from 'zod'
import { fetchHistory } from '@/api/chat'
import { AuthError } from '@/api/errors'
import { LanguageSwitcher } from '@/components/language-switcher'
import { ThemeToggle } from '@/components/theme-toggle'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { useAuth } from '@/lib/auth'
import { setAccessCode } from '@/lib/storage'
import { toastError } from '@/lib/errors'

export default function AccessPage() {
  const { t } = useTranslation()
  const { hasAccess, signIn } = useAuth()
  const navigate = useNavigate()

  // Messages are translated lazily, so they follow the language switcher.
  const schema = z.object({
    code: z.string().trim().min(1, 'access.required').max(200, 'access.tooLong'),
  })
  type Values = z.infer<typeof schema>

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { code: '' } })

  if (hasAccess) return <Navigate to="/chat" replace />

  const onSubmit = async ({ code }: Values) => {
    // The API client reads the code from storage. Put it there first, prove it works with a cheap
    // call, and only then flip the auth state (doing it earlier would redirect away mid-check).
    setAccessCode(code)
    try {
      await fetchHistory()
      signIn(code)
      navigate('/chat', { replace: true })
    } catch (e) {
      // On 401/403 the client has already cleared the code and flipped the auth state.
      if (e instanceof AuthError) setError('code', { message: 'access.wrong' })
      else {
        toastError(e)
        signIn(code)
        navigate('/chat', { replace: true }) // server unreachable: let the user in, chat will show the error
      }
    }
  }

  return (
    <div className="relative grid min-h-dvh place-items-center bg-background px-4">
      <div className="absolute top-4 right-4 flex gap-2">
        <LanguageSwitcher />
        <ThemeToggle />
      </div>
      <Card className="w-full max-w-sm p-6">
        <div className="mb-5 grid size-10 place-items-center rounded-md bg-accent text-accent-foreground">
          <BookOpen className="size-5" />
        </div>
        <h1 className="text-xl font-semibold tracking-tight">{t('access.title')}</h1>
        <p className="mt-1.5 text-sm text-muted-foreground">{t('access.description')}</p>
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="mt-5 space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="code" className="text-sm font-medium">
              {t('access.label')}
            </label>
            <Input
              id="code"
              type="password"
              autoComplete="off"
              autoFocus
              placeholder={t('access.placeholder')}
              aria-invalid={!!errors.code}
              aria-describedby={errors.code ? 'code-error' : undefined}
              {...register('code')}
            />
            {errors.code?.message && (
              <p id="code-error" role="alert" className="text-sm text-destructive">
                {t(errors.code.message)}
              </p>
            )}
          </div>
          <Button type="submit" className="w-full" disabled={isSubmitting}>
            {isSubmitting ? t('access.checking') : t('access.submit')}
          </Button>
        </form>
      </Card>
    </div>
  )
}
