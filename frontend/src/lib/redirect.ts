/** The page a visitor was sent away from (RequireAuth stores it in the router state), or /chat. */
export function fromPath(state: unknown): string {
  const from = (state as { from?: { pathname?: string; search?: string } } | null)?.from
  // Only in-app paths: the value comes from router state, but never let it become an open redirect.
  if (from?.pathname?.startsWith('/') && !from.pathname.startsWith('//')) {
    return `${from.pathname}${from.search ?? ''}`
  }
  return '/chat'
}
