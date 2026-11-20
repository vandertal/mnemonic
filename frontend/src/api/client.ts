import { clearAccessCode, getAccessCode } from '@/lib/storage'
import { ApiError, AuthError, NetworkError } from './errors'

export const API_URL = (import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')

// The router registers a callback here, so this module needs no knowledge of React.
let onAuthFailure: () => void = () => {}
export function setAuthFailureHandler(fn: () => void) {
  onAuthFailure = fn
}

async function detailOf(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body?.detail === 'string') return body.detail
  } catch {
    /* not JSON */
  }
  return res.statusText || `HTTP ${res.status}`
}

/** fetch + X-API-Key + typed errors. Returns the Response (so callers can stream it). */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  const code = getAccessCode()
  if (code) headers.set('X-API-Key', code)

  let res: Response
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e // not a failure: the user stopped it
    throw new NetworkError()
  }
  if (res.status === 401 || res.status === 403) {
    clearAccessCode()
    onAuthFailure()
    throw new AuthError(res.status, await detailOf(res))
  }
  if (!res.ok) throw new ApiError(res.status, await detailOf(res))
  return res
}

export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await apiFetch(path, init)
  return (await res.json()) as T
}
