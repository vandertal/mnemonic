// All localStorage access in one place. Every call is wrapped: storage can throw
// (private mode, blocked site data) and the app must still work without it.
const KEYS = {
  accessCode: 'mnemonic.accessCode',
  sessionId: 'mnemonic.sessionId',
  ownerId: 'mnemonic.ownerId',
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

/** A random UUID kept in localStorage. NOT authentication: it only separates one browser's data from another's. */
export function getOrCreateId(key: 'sessionId' | 'ownerId'): string {
  const existing = readStored(key)
  if (existing) return existing
  const id = crypto.randomUUID()
  writeStored(key, id)
  return id
}

export const getAccessCode = () => readStored('accessCode')
export const setAccessCode = (code: string) => writeStored('accessCode', code)
export const clearAccessCode = () => removeStored('accessCode')
