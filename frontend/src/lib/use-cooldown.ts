import { useCallback, useEffect, useState } from 'react'

/**
 * A countdown that can be (re)started: whole seconds left, ticking every second.
 * The login/register forms start it from a 429's Retry-After and keep the submit button
 * disabled until it reaches 0.
 */
export function useCooldown(): { left: number; start: (seconds: number) => void } {
  const [endsAt, setEndsAt] = useState(0)
  const [now, setNow] = useState(() => Date.now())
  const left = Math.max(0, Math.ceil((endsAt - now) / 1000))

  useEffect(() => {
    if (left === 0) return
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [left === 0]) // eslint-disable-line react-hooks/exhaustive-deps -- only the running/stopped edge matters

  const start = useCallback((seconds: number) => {
    const t = Date.now()
    setNow(t)
    setEndsAt(t + seconds * 1000)
  }, [])
  return { left, start }
}
