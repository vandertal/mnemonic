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
const LoginPage = lazy(() => import('@/pages/login-page'))
const RegisterPage = lazy(() => import('@/pages/register-page'))
const ChatPage = lazy(() => import('@/pages/chat-page'))
const DocumentsPage = lazy(() => import('@/pages/documents-page'))
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
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route element={<RequireAuth />}>
                <Route element={<AppShell />}>
                  <Route index element={<Navigate to="/chat" replace />} />
                  <Route path="/chat/:sessionId?" element={<ChatPage />} />
                  <Route path="/documents" element={<DocumentsPage />} />
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
