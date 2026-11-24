import { useEffect, useState } from 'react'

/** Whole seconds left until `seconds` from now have passed; ticks every second, stops at 0. */
export function useCountdown(seconds: number | undefined): number {
  const [endsAt] = useState(() => Date.now() + (seconds ?? 0) * 1000)
  const [now, setNow] = useState(() => Date.now())
  const remaining = Math.max(0, Math.ceil((endsAt - now) / 1000))
  const finished = remaining === 0
  useEffect(() => {
    if (finished) return
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [finished])
  return remaining
}
