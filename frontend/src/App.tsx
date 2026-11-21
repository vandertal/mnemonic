import { lazy, Suspense } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { Toaster } from 'sonner'
import { AppShell } from '@/components/layout/app-shell'
import { AuthProvider, useAuth } from '@/lib/auth'
import { SessionsProvider } from '@/lib/sessions'
import { queryClient } from '@/lib/query'
import { ThemeProvider, useTheme } from '@/lib/theme'
import { PageFallback } from '@/components/page-fallback'
import { usePageTitle } from '@/lib/page-title'

// Each page is its own chunk: the first paint only downloads the code of the page being opened.
const AccessPage = lazy(() => import('@/pages/access-page'))
const ChatPage = lazy(() => import('@/pages/chat-page'))
const DocumentsPage = lazy(() => import('@/pages/documents-page'))
const FlashcardsPage = lazy(() => import('@/pages/flashcards-page'))
const NotFoundPage = lazy(() => import('@/pages/not-found-page'))
const SettingsPage = lazy(() => import('@/pages/settings-page'))

/** Everything inside needs the access code; without it (or after a 401) go to /access. */
function RequireAccess() {
  const { hasAccess } = useAuth()
  return hasAccess ? <Outlet /> : <Navigate to="/access" replace />
}

/** Sessions exist only behind the gate; the shell and the chat page share them. */
function SessionShell() {
  return (
    <SessionsProvider>
      <AppShell />
    </SessionsProvider>
  )
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
              <Route path="/access" element={<AccessPage />} />
              <Route element={<RequireAccess />}>
                <Route element={<SessionShell />}>
                  <Route index element={<Navigate to="/chat" replace />} />
                  <Route path="/chat" element={<ChatPage />} />
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
