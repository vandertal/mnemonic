// Quick check that a running backend accepts this SPA. Node 20+, no dependencies.
// Usage (PowerShell):
//   $env:SMOKE_ORIGIN = "https://your-spa.example"; npm run smoke
// Env: SMOKE_ORIGIN (default http://localhost:5173), SMOKE_API (default VITE_API_URL from .env, then
// http://127.0.0.1:8000), SMOKE_INVITE (only if the server sets REGISTRATION_CODE).
// It registers a throwaway user and deletes it again. Auth endpoints allow 5 calls/min per IP:
// this script makes 2 (register, login) plus the cleanup DELETE /auth/me, which is not limited.
import { randomBytes } from 'node:crypto'
import { readEnv } from './env.mjs'

const env = readEnv()
const api = (env.SMOKE_API || env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
const origin = env.SMOKE_ORIGIN || 'http://localhost:5173'
const invite = env.SMOKE_INVITE

const email = `smoke-${randomBytes(6).toString('hex')}@example.com`
const password = randomBytes(18).toString('base64url') // never printed

let failed = false
async function check(name, fn) {
  try {
    const problem = await fn()
    console.log(`${problem ? 'FAIL' : 'PASS'}  ${name}${problem ? ` -> ${problem}` : ''}`)
    if (problem) failed = true
    return !problem
  } catch (e) {
    console.log(`FAIL  ${name} -> ${e instanceof Error ? e.message : e}`)
    failed = true
    return false
  }
}
const expectStatus = (res, want) => (res.status === want ? null : `expected ${want}, got ${res.status}`)

console.log(`API ${api}  origin ${origin}`)

await check('CORS preflight OPTIONS /sessions with Authorization', async () => {
  const res = await fetch(`${api}/sessions`, {
    method: 'OPTIONS',
    headers: {
      Origin: origin,
      'Access-Control-Request-Method': 'GET',
      'Access-Control-Request-Headers': 'authorization,content-type',
    },
  })
  const allowed = res.headers.get('access-control-allow-origin')
  const headers = (res.headers.get('access-control-allow-headers') || '').toLowerCase()
  return (
    expectStatus(res, 200) ??
    (allowed === origin ? null : `allow-origin is "${allowed}"`) ??
    (headers.includes('authorization') ? null : 'Authorization is not an allowed header')
  )
})

let token = null
const registered = await check('POST /auth/register (random user) -> 201', async () => {
  const res = await fetch(`${api}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, ...(invite ? { registration_code: invite } : {}) }),
  })
  if (res.status === 403) return 'registration code needed: set SMOKE_INVITE'
  if (res.status === 429) return 'rate limited (5 auth calls/min): wait a minute'
  return expectStatus(res, 201)
})

if (registered) {
  await check('POST /auth/login (form-encoded) -> 200 + token', async () => {
    const res = await fetch(`${api}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ username: email, password }),
    })
    if (res.status !== 200) return expectStatus(res, 200)
    token = (await res.json()).access_token ?? null
    return token ? null : 'no access_token in the response'
  })

  if (token) {
    await check('GET /sessions with token -> 200', async () =>
      expectStatus(await fetch(`${api}/sessions`, { headers: { Authorization: `Bearer ${token}` } }), 200),
    )
    await check('GET /sessions without token -> 401', async () => expectStatus(await fetch(`${api}/sessions`), 401))
  }

  // Cleanup runs even when a check above failed, so no test account is left behind.
  if (token) {
    await check('DELETE /auth/me -> 204 (cleanup)', async () =>
      expectStatus(await fetch(`${api}/auth/me`, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } }), 204),
    )
  } else {
    console.log(`WARN  no token, so the test account ${email} could not be deleted`)
  }
}

process.exit(failed ? 1 : 0)
