import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import * as authApi from '@/api/auth'
import { setAuthFailureHandler } from '@/api/client'
import type { User } from '@/api/types'
import { removeDecks } from '@/features/flashcards/decks'
import { clearChunkCache } from '@/features/chat/use-chunk'
import i18n from '@/i18n'
import { clearToken, getToken, setToken } from './storage'

const ME_KEY = ['auth', 'me'] as const

type AuthStatus = 'anonymous' | 'loading' | 'error' | 'authenticated'

interface AuthValue {
  status: AuthStatus
  user: User | null
  /** Where RequireAuth sends a signed-out visitor: /register right after the account was deleted. */
  anonRoute: '/login' | '/register'
  retry: () => void
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, registrationCode?: string) => Promise<void>
  logout: () => void
  deleteAccount: () => Promise<void>
}

const AuthContext = createContext<AuthValue | null>(null)

/**
 * The token lives in localStorage (so a reload keeps you signed in); the server stays the judge:
 * a stored token is only trusted after GET /auth/me accepts it.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const [token, setTokenState] = useState(getToken)
  const [anonRoute, setAnonRoute] = useState<AuthValue['anonRoute']>('/login')

  // One account must never see another's cached data: drop every query (and the chunk cache) on any change.
  const resetCaches = useCallback(() => {
    void qc.cancelQueries()
    qc.clear()
    clearChunkCache()
  }, [qc])

  // The API client calls this on a 401 (after it already removed the stored token).
  useEffect(() => {
    setAuthFailureHandler(() => {
      resetCaches()
      setAnonRoute('/login')
      setTokenState(null)
      toast.error(i18n.t('auth.sessionExpired'))
    })
  }, [resetCaches])

  const me = useQuery({ queryKey: ME_KEY, queryFn: authApi.fetchMe, enabled: !!token, staleTime: Infinity })

  const login = useCallback(
    async (email: string, password: string) => {
      const next = await authApi.login(email, password)
      setToken(next)
      resetCaches()
      setAnonRoute('/login')
      setTokenState(next)
    },
    [resetCaches],
  )

  const register = useCallback(
    async (email: string, password: string, registrationCode?: string) => {
      await authApi.register(email, password, registrationCode)
      await login(email, password)
    },
    [login],
  )

  const logout = useCallback(() => {
    clearToken()
    resetCaches()
    setAnonRoute('/login')
    setTokenState(null)
  }, [resetCaches])

  const user = me.data ?? null
  const deleteAccount = useCallback(async () => {
    await authApi.deleteAccount()
    if (user) removeDecks(user.id)
    clearToken()
    resetCaches()
    setAnonRoute('/register')
    setTokenState(null)
  }, [user, resetCaches])

  const status: AuthStatus = !token ? 'anonymous' : user ? 'authenticated' : me.isError ? 'error' : 'loading'
  const { refetch } = me
  const retry = useCallback(() => void refetch(), [refetch])

  const value = useMemo(
    () => ({ status, user, anonRoute, retry, login, register, logout, deleteAccount }),
    [status, user, anonRoute, retry, login, register, logout, deleteAccount],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}

/** For screens behind RequireAuth, where the user is always there. */
// eslint-disable-next-line react-refresh/only-export-components
export function useCurrentUser(): User {
  const { user } = useAuth()
  if (!user) throw new Error('useCurrentUser needs a signed-in user (use it behind RequireAuth)')
  return user
}
