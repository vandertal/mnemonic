// All localStorage access in one place. Every call is wrapped: storage can throw
// (private mode, blocked site data) and the app must still work without it.
const KEYS = {
  token: 'mnemonic.token',
  theme: 'mnemonic.theme',
  lang: 'mnemonic.lang',
  sidebar: 'mnemonic.sidebarCollapsed',
} as const

export function readStored(key: keyof typeof KEYS): string | null {
  try {
    return localStorage.getItem(KEYS[key])
  } catch {
    return null
  }
}

export function writeStored(key: keyof typeof KEYS, value: string): void {
  try {
    localStorage.setItem(KEYS[key], value)
  } catch {
    /* ignore: the value just will not persist */
  }
}

export function removeStored(key: keyof typeof KEYS): void {
  try {
    localStorage.removeItem(KEYS[key])
  } catch {
    /* ignore */
  }
}

/** JSON under a free-form key (e.g. per-owner decks). Corrupt or missing data gives the fallback. */
export function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(`mnemonic.${key}`)
    return raw === null ? fallback : (JSON.parse(raw) as T)
  } catch {
    return fallback
  }
}

export function writeJson(key: string, value: unknown): void {
  try {
    localStorage.setItem(`mnemonic.${key}`, JSON.stringify(value))
  } catch {
    /* quota or blocked storage: the data just will not persist */
  }
}

export function removeJson(key: string): void {
  try {
    localStorage.removeItem(`mnemonic.${key}`)
  } catch {
    /* ignore */
  }
}

// The JWT. localStorage is readable by any script on the page (XSS): see frontend/README.md.
export const getToken = () => readStored('token')
export const setToken = (token: string) => writeStored('token', token)
export const clearToken = () => removeStored('token')
