import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { setAuthFailureHandler } from '@/api/client'
import { clearAccessCode, getAccessCode, setAccessCode } from './storage'

interface AuthValue {
  hasAccess: boolean
  signIn: (code: string) => void
  signOut: () => void
}

const AuthContext = createContext<AuthValue | null>(null)

/** Access-code "session". NOT real auth (that arrives in lab 21): it only decides which screens show. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [hasAccess, setHasAccess] = useState(() => !!getAccessCode())

  const signIn = useCallback((code: string) => {
    setAccessCode(code)
    setHasAccess(true)
  }, [])
  const signOut = useCallback(() => {
    clearAccessCode()
    setHasAccess(false)
  }, [])

  // The API client calls this on 401/403, after it already cleared the stored code.
  useEffect(() => {
    setAuthFailureHandler(() => setHasAccess(false))
  }, [])

  const value = useMemo(() => ({ hasAccess, signIn, signOut }), [hasAccess, signIn, signOut])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
