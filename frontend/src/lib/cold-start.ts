// Render's free plan puts the API to sleep; the first request after a pause waits up to a minute.
// apiFetch reports every request here. A request that is still pending after SLOW_AFTER_MS marks
// the server as "waking up" until that request (or any other) gets an answer. No React in here, so
// it is unit-tested with fake timers; the banner reads it through useSyncExternalStore.

export const SLOW_AFTER_MS = 4000

/** Requests that legitimately take long (an LLM answer): never evidence of a sleeping server. */
const LONG_BY_DESIGN = ['/chat', '/flashcards', '/documents']

let pending = 0
let wakingSince: number | null = null
const listeners = new Set<() => void>()

function emit() {
  for (const l of listeners) l()
}

export function subscribeCold(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** Epoch ms when the server first looked asleep, or null. A stable value between changes. */
export const getWakingSince = () => wakingSince

/** Call when a request starts; call the returned function when it ends (answer, error or abort). */
export function trackRequest(path: string, method = 'GET'): () => void {
  const upper = method.toUpperCase()
  const longByDesign = upper !== 'GET' && LONG_BY_DESIGN.some((p) => path.startsWith(p))
  if (longByDesign) return () => {}

  pending++
  const timer = setTimeout(() => {
    if (wakingSince === null) {
      wakingSince = Date.now()
      emit()
    }
  }, SLOW_AFTER_MS)

  let finished = false
  return () => {
    if (finished) return
    finished = true
    clearTimeout(timer)
    pending--
    if (wakingSince !== null) {
      // An answer arrived: the server is up. (Other slow requests will re-arm on their own.)
      wakingSince = null
      emit()
    }
  }
}

/** Tests only. */
export function resetColdStart() {
  pending = 0
  wakingSince = null
  listeners.clear()
}

export const pendingCount = () => pending
