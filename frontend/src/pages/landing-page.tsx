import { ArrowRight, BookOpen, Layers, Lock, MessageSquare, Quote, Search, SearchX, Send, ShieldCheck } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { LanguageSwitcher } from '@/components/language-switcher'
import { ThemeToggle } from '@/components/theme-toggle'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { ChatMock } from '@/features/landing/chat-mock'
import { telegramBotUrl } from '@/lib/telegram'

const GITHUB_URL = 'https://github.com/vandertal/mnemonic'

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="mx-auto w-full max-w-6xl px-4 py-14 sm:px-6 sm:py-20">
      <h2 id={id} className="text-center text-2xl font-semibold tracking-tight sm:text-3xl">
        {title}
      </h2>
      {children}
    </section>
  )
}

function IconBadge({ children }: { children: ReactNode }) {
  return (
    <div className="grid size-10 place-items-center rounded-lg bg-accent-soft text-accent" aria-hidden="true">
      {children}
    </div>
  )
}

const STEPS = [
  { icon: MessageSquare, n: 1 },
  { icon: ShieldCheck, n: 2 },
  { icon: Layers, n: 3 },
] as const

const FEATURES = [
  { icon: Quote, n: 1 },
  { icon: SearchX, n: 2 },
  { icon: Search, n: 3 },
] as const

/** Keeps the search-engine description in step with the page language; restores it on leaving. */
function useMetaDescription(text: string) {
  useEffect(() => {
    const el = document.querySelector('meta[name="description"]')
    const previous = el?.getAttribute('content')
    el?.setAttribute('content', text)
    return () => {
      if (previous != null) el?.setAttribute('content', previous)
    }
  }, [text])
}

/** The public front page (`/` for signed-out visitors): one promise, one button, proof below. */
export default function LandingPage() {
  const { t } = useTranslation()
  useMetaDescription(t('landing.metaDescription'))
  const telegramUrl = telegramBotUrl() // null unless the build sets VITE_TELEGRAM_BOT_URL

  return (
    <div className="relative min-h-dvh overflow-x-clip bg-background text-foreground">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-card px-3 py-2 text-sm font-medium shadow-md focus:not-sr-only focus:absolute focus:top-3 focus:left-3"
      >
        {t('landing.skip')}
      </a>
      {/* Soft brand glow behind the hero. Decorative; costs no request and cannot shift anything. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-[34rem] bg-[radial-gradient(60%_60%_at_50%_0%,color-mix(in_oklab,var(--accent)_16%,transparent),transparent)]"
      />

      <header className="relative mx-auto flex h-16 w-full max-w-6xl items-center justify-between gap-3 px-4 sm:px-6">
        <Link to="/" className="flex items-center gap-2.5 rounded-md" aria-label={t('app.name')}>
          <span className="grid size-8 place-items-center rounded-md bg-accent text-accent-foreground">
            <BookOpen className="size-4" aria-hidden="true" />
          </span>
          <span className="text-[15px] font-semibold tracking-tight">{t('app.name')}</span>
        </Link>
        <nav aria-label={t('landing.navLabel')} className="flex items-center gap-2">
          <div className="hidden items-center gap-2 sm:flex">
            <LanguageSwitcher />
            <ThemeToggle />
          </div>
          <Button asChild variant="ghost" size="sm">
            <Link to="/login">{t('landing.login')}</Link>
          </Button>
          <Button asChild size="sm" className="hidden sm:inline-flex">
            <Link to="/register">{t('landing.tryIt')}</Link>
          </Button>
        </nav>
      </header>

      <main id="main" className="relative">
        <section className="mx-auto grid w-full max-w-6xl items-center gap-10 px-4 pt-8 pb-14 sm:px-6 sm:pt-14 lg:grid-cols-2 lg:gap-14 lg:pb-24">
          <div className="text-center lg:text-left">
            <p className="inline-flex items-center gap-1.5 rounded-full border bg-card px-3 py-1 text-xs font-medium text-muted-foreground shadow-sm">
              <ShieldCheck className="size-3.5 text-accent" aria-hidden="true" />
              {t('landing.eyebrow')}
            </p>
            <h1 className="mt-5 text-4xl leading-[1.1] font-semibold tracking-tight text-balance sm:text-5xl">
              {t('landing.heroTitle')}
            </h1>
            <p className="mx-auto mt-5 max-w-xl text-base text-pretty text-muted-foreground sm:text-lg lg:mx-0">
              {t('landing.heroSub')}
            </p>
            <div className="mt-8 flex flex-col items-center gap-3 sm:flex-row sm:justify-center lg:justify-start">
              <Button asChild className="h-11 w-full px-6 text-base sm:w-auto">
                <Link to="/register">
                  {t('landing.tryIt')}
                  <ArrowRight className="size-4" aria-hidden="true" />
                </Link>
              </Button>
              <Button asChild variant="outline" className="h-11 w-full px-6 text-base sm:w-auto">
                <Link to="/login">{t('landing.login')}</Link>
              </Button>
            </div>
            <p className="mx-auto mt-4 max-w-md text-sm text-muted-foreground lg:mx-0">{t('landing.tryHint')}</p>
            {telegramUrl && (
              <p className="mt-3 text-sm">
                <a
                  href={telegramUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  data-testid="telegram-hero"
                  className="inline-flex items-center gap-1.5 rounded-sm font-medium text-accent underline-offset-4 hover:underline"
                >
                  <Send className="size-3.5" aria-hidden="true" />
                  {t('landing.telegram')}
                </a>
              </p>
            )}
          </div>
          <div className="mx-auto w-full max-w-xl">
            <ChatMock />
          </div>
        </section>

        <Section id="steps-title" title={t('landing.stepsTitle')}>
          <ol className="mt-10 grid gap-4 sm:grid-cols-3">
            {STEPS.map(({ icon: Icon, n }) => (
              <li key={n}>
                <Card className="h-full p-5">
                  <div className="flex items-center gap-3">
                    <IconBadge>
                      <Icon className="size-5" />
                    </IconBadge>
                    <span className="text-sm font-medium text-muted-foreground tabular-nums">{n}</span>
                  </div>
                  <h3 className="mt-4 text-base font-semibold">{t(`landing.step${n}Title`)}</h3>
                  <p className="mt-1.5 text-sm text-muted-foreground">{t(`landing.step${n}Text`)}</p>
                </Card>
              </li>
            ))}
          </ol>
        </Section>

        <Section id="features-title" title={t('landing.featuresTitle')}>
          <ul className="mt-10 grid gap-4 sm:grid-cols-3">
            {FEATURES.map(({ icon: Icon, n }) => (
              <li key={n}>
                <Card className="h-full p-5">
                  <IconBadge>
                    <Icon className="size-5" />
                  </IconBadge>
                  <h3 className="mt-4 text-base font-semibold">{t(`landing.f${n}Title`)}</h3>
                  <p className="mt-1.5 text-sm text-muted-foreground">{t(`landing.f${n}Text`)}</p>
                </Card>
              </li>
            ))}
          </ul>
        </Section>

        <section aria-labelledby="privacy-title" className="mx-auto w-full max-w-3xl px-4 pb-14 sm:px-6">
          <div className="flex gap-4 rounded-xl border bg-card p-5 shadow-sm">
            <IconBadge>
              <Lock className="size-5" />
            </IconBadge>
            <div>
              <h2 id="privacy-title" className="text-base font-semibold">
                {t('landing.privacyTitle')}
              </h2>
              <p className="mt-1.5 text-sm text-muted-foreground">{t('landing.privacyText')}</p>
            </div>
          </div>
        </section>

        <section aria-labelledby="cta-title" className="mx-auto w-full max-w-6xl px-4 pb-20 sm:px-6">
          <div className="rounded-2xl border bg-accent-soft px-6 py-12 text-center">
            <h2 id="cta-title" className="text-2xl font-semibold tracking-tight text-balance">
              {t('landing.ctaTitle')}
            </h2>
            <Button asChild className="mt-6 h-11 px-6 text-base">
              <Link to="/register">
                {t('landing.tryIt')}
                <ArrowRight className="size-4" aria-hidden="true" />
              </Link>
            </Button>
          </div>
        </section>
      </main>

      <footer className="relative border-t">
        <div className="mx-auto flex w-full max-w-6xl flex-col items-center gap-4 px-4 py-8 text-sm text-muted-foreground sm:flex-row sm:justify-between sm:px-6">
          <p>
            {t('app.name')} · {t('landing.footerProject')}
          </p>
          <div className="flex flex-wrap items-center justify-center gap-4">
            <div className="flex items-center gap-2 sm:hidden">
              <LanguageSwitcher />
              <ThemeToggle />
            </div>
            {telegramUrl && (
              <a
                href={telegramUrl}
                target="_blank"
                rel="noopener noreferrer"
                data-testid="telegram-footer"
                className="rounded-sm font-medium text-foreground underline-offset-4 hover:underline"
              >
                {t('landing.telegram')}
              </a>
            )}
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-sm font-medium text-foreground underline-offset-4 hover:underline"
            >
              {t('landing.github')}
            </a>
          </div>
        </div>
      </footer>
    </div>
  )
}
