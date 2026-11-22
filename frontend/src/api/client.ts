import { clearToken, getToken } from '@/lib/storage'
import { NetworkError, errorForStatus, isAbort } from './errors'

export const API_URL = (import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')

// The auth provider registers a callback here, so this module needs no knowledge of React.
let onAuthFailure: () => void = () => {}
export function setAuthFailureHandler(fn: () => void) {
  onAuthFailure = fn
}

async function detailOf(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body?.detail === 'string') return body.detail
  } catch {
    /* not JSON, or FastAPI's 422 list */
  }
  return res.statusText || `HTTP ${res.status}`
}

interface Options extends RequestInit {
  /** Login only: a 401 there means "wrong password", not "your token died", so it must not log anyone out. */
  skipAuthFailure?: boolean
}

/** fetch + Bearer token + typed errors. Returns the Response (so callers can stream it). */
export async function apiFetch(path: string, { skipAuthFailure, ...init }: Options = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let res: Response
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers })
  } catch (e) {
    if (isAbort(e)) throw e // not a failure: the user stopped it
    throw new NetworkError()
  }
  if (!res.ok) {
    const error = errorForStatus(res.status, await detailOf(res))
    // Every call goes through here, SSE streams included (their 401 arrives as the response status).
    if (res.status === 401 && !skipAuthFailure) {
      clearToken()
      onAuthFailure()
    }
    throw error
  }
  return res
}

export async function apiJson<T>(path: string, init?: Options): Promise<T> {
  const res = await apiFetch(path, init)
  return (await res.json()) as T
}

export const jsonBody = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})
