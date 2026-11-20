import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { Toaster } from 'sonner'
import { AppShell } from '@/components/layout/app-shell'
import { AuthProvider, useAuth } from '@/lib/auth'
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

function ThemedToaster() {
  const { theme } = useTheme()
  return <Toaster theme={theme} position="top-center" richColors closeButton />
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/access" element={<AccessPage />} />
            <Route element={<RequireAccess />}>
              <Route element={<AppShell />}>
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
    </ThemeProvider>
  )
}
