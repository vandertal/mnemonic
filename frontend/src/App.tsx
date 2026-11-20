import { QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { Toaster } from 'sonner'
import { AppShell } from '@/components/layout/app-shell'
import { AuthProvider, useAuth } from '@/lib/auth'
import { SessionsProvider } from '@/lib/sessions'
import { queryClient } from '@/lib/query'
import { ThemeProvider, useTheme } from '@/lib/theme'
import AccessPage from '@/pages/access-page'
import ChatPage from '@/pages/chat-page'
import DocumentsPage from '@/pages/documents-page'
import FlashcardsPage from '@/pages/flashcards-page'
import NotFoundPage from '@/pages/not-found-page'
import SettingsPage from '@/pages/settings-page'

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
          </BrowserRouter>
          <ThemedToaster />
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  )
}
