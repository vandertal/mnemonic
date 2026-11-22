import { apiFetch, apiJson, jsonBody } from './client'
import type { User } from './types'

export function register(email: string, password: string, registrationCode?: string): Promise<User> {
  return apiJson<User>('/auth/register', {
    ...jsonBody({ email, password, ...(registrationCode ? { registration_code: registrationCode } : {}) }),
    skipAuthFailure: true,
  })
}

/** OAuth2 password form: the server expects form encoding and calls the email field `username`. */
export async function login(email: string, password: string): Promise<string> {
  const { access_token } = await apiJson<{ access_token: string }>('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ username: email, password }),
    skipAuthFailure: true,
  })
  return access_token
}

export const fetchMe = () => apiJson<User>('/auth/me')

export async function deleteAccount(): Promise<void> {
  await apiFetch('/auth/me', { method: 'DELETE' })
}
