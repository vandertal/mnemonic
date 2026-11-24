import { lazy, Suspense } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Toaster } from 'sonner'
import { AppShell } from '@/components/layout/app-shell'
import { AuthProvider, useAuth } from '@/lib/auth'
import { queryClient } from '@/lib/query'
import { ThemeProvider, useTheme } from '@/lib/theme'
import { PageFallback } from '@/components/page-fallback'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/card'
import { usePageTitle } from '@/lib/page-title'

// Each page is its own chunk: the first paint only downloads the code of the page being opened.
const LandingPage = lazy(() => import('@/pages/landing-page'))
const LoginPage = lazy(() => import('@/pages/login-page'))
const RegisterPage = lazy(() => import('@/pages/register-page'))
const ChatPage = lazy(() => import('@/pages/chat-page'))
const DocumentsPage = lazy(() => import('@/pages/documents-page'))
const SearchPage = lazy(() => import('@/pages/search-page'))
const FlashcardsPage = lazy(() => import('@/pages/flashcards-page'))
const NotFoundPage = lazy(() => import('@/pages/not-found-page'))
const SettingsPage = lazy(() => import('@/pages/settings-page'))

/**
 * Everything inside needs a signed-in user. No token: go to /login and remember where the visitor
 * was headed. A stored token is trusted only after GET /auth/me accepts it (skeleton meanwhile).
 */
function RequireAuth() {
  const { t } = useTranslation()
  const { status, anonRoute, retry } = useAuth()
  const location = useLocation()
  if (status === 'anonymous') return <Navigate to={anonRoute} state={{ from: location }} replace />
  if (status === 'loading') {
    return (
      <div className="flex h-dvh bg-background" role="status" aria-label={t('common.loading')}>
        <Skeleton className="hidden h-full w-64 rounded-none md:block" />
        <div className="flex-1 space-y-3 p-6">
          <Skeleton className="h-8 w-1/3" />
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-4 w-1/2" />
        </div>
      </div>
    )
  }
  if (status === 'error') {
    // The token was not judged (server or network trouble): do not log out, let the user retry.
    return (
      <div className="grid h-dvh place-items-center bg-background px-4 text-center">
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">{t('auth.checkFailed')}</p>
          <Button onClick={retry}>{t('chat.retry')}</Button>
        </div>
      </div>
    )
  }
  return <Outlet />
}

/**
 * `/`: the landing page for signed-out visitors, the app for everyone else. While a stored token is
 * still being checked we show the skeleton instead of flashing the landing page at a signed-in user.
 */
function Home() {
  const { status } = useAuth()
  if (status === 'loading') return <PageFallback />
  if (status === 'anonymous') return <LandingPage />
  return <Navigate to="/chat" replace /> // authenticated; on 'error' RequireAuth offers the retry
}

/** Keeps document.title in sync with the route (and the language). Renders nothing. */
function PageTitle() {
  usePageTitle()
  return null
}

function ThemedToaster() {
  const { theme } = useTheme()
  return <Toaster theme={theme} position="top-center" richColors closeButton />
}

export default function App() {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <BrowserRouter>
            <PageTitle />
            <Suspense fallback={<PageFallback />}>
              <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route element={<RequireAuth />}>
                <Route element={<AppShell />}>
                  <Route path="/chat/:sessionId?" element={<ChatPage />} />
                  <Route path="/documents" element={<DocumentsPage />} />
                  <Route path="/search" element={<SearchPage />} />
                  <Route path="/flashcards" element={<FlashcardsPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                </Route>
              </Route>
              <Route path="*" element={<NotFoundPage />} />
              </Routes>
            </Suspense>
          </BrowserRouter>
          <ThemedToaster />
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
