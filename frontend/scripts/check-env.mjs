// Runs before `npm run dev` and as `npm run doctor`. Node 20+, no dependencies.
// 1) Warns when VITE_API_URL is missing or local.
// 2) If it is set, asks the API for its OpenAPI schema and checks that it is THIS lab's API
//    (accounts + sessions). Exits non-zero with one clear line otherwise, so `npm run dev` does not
//    start an SPA that can only show errors.
import { readEnv } from './env.mjs'

const REQUIRED_PATHS = ['/auth/register', '/sessions']
const LOCAL_TIMEOUT_MS = 10_000
const REMOTE_TIMEOUT_MS = 70_000 // Render's free plan sleeps; waking it up takes up to a minute

const url = readEnv().VITE_API_URL?.trim().replace(/\/$/, '')
const local = url && /^https?:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/i.test(url)

console.log(`[env] API URL: ${url || '(not set: the app falls back to http://127.0.0.1:8000)'}`)
if (!url || local) {
  const bar = '!'.repeat(64)
  console.warn(
    `\n${bar}\n!! WARNING: VITE_API_URL is ${url ? 'a LOCAL address' : 'MISSING'}.\n` +
      `!! Chat/documents will fail unless a backend runs there.\n` +
      `!! Copy .env.example to .env for the deployed backend.\n${bar}\n`,
  )
}

if (url) {
  const timeout = local ? LOCAL_TIMEOUT_MS : REMOTE_TIMEOUT_MS
  if (!local) console.log(`[env] checking ${url}/openapi.json (a sleeping Render service can take up to a minute)...`)
  const problem = await checkApi(url, timeout)
  if (problem) {
    console.error(`[env] FAIL: ${problem}`)
    process.exit(1)
  }
  console.log('[env] OK: the API has /auth/register and /sessions')
}

/** null when the API looks right, otherwise a one-line reason. */
async function checkApi(base, timeoutMs) {
  let res
  try {
    res = await fetch(`${base}/openapi.json`, { signal: AbortSignal.timeout(timeoutMs) })
  } catch (e) {
    const why = e?.name === 'TimeoutError' ? `no answer in ${timeoutMs / 1000} s` : (e?.cause?.code ?? e?.message)
    return `API unreachable at ${base} (${why}): is the backend running / is VITE_API_URL right?`
  }
  if (!res.ok) return `${base}/openapi.json answered HTTP ${res.status}: wrong VITE_API_URL?`
  let paths
  try {
    paths = Object.keys((await res.json()).paths ?? {})
  } catch {
    return `${base}/openapi.json is not JSON: wrong VITE_API_URL?`
  }
  const missing = REQUIRED_PATHS.find((p) => !paths.includes(p))
  return missing ? `this API has no ${missing}: wrong VITE_API_URL or an old deploy` : null
}
