// Quick check that the deployed backend accepts this SPA. Node 20+, no dependencies.
// Usage: SMOKE_KEY=<access code> npm run smoke   (SMOKE_ORIGIN defaults to http://localhost:5173)
import { randomUUID } from 'node:crypto'
import { readEnv } from './env.mjs'

const env = readEnv()
const api = (env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '')
const key = env.SMOKE_KEY
const origin = env.SMOKE_ORIGIN || 'http://localhost:5173'
const zero = '00000000-0000-0000-0000-000000000000'

let failed = false
async function check(name, fn) {
  try {
    const problem = await fn()
    console.log(`${problem ? 'FAIL' : 'PASS'}  ${name}${problem ? ` -> ${problem}` : ''}`)
    if (problem) failed = true
  } catch (e) {
    console.log(`FAIL  ${name} -> ${e instanceof Error ? e.message : e}`)
    failed = true
  }
}
const expectStatus = (res, want) => (res.status === want ? null : `expected ${want}, got ${res.status}`)

console.log(`API ${api}  origin ${origin}`)

await check('CORS preflight OPTIONS /chat', async () => {
  const res = await fetch(`${api}/chat`, {
    method: 'OPTIONS',
    headers: {
      Origin: origin,
      'Access-Control-Request-Method': 'POST',
      'Access-Control-Request-Headers': 'x-api-key,content-type',
    },
  })
  const allowed = res.headers.get('access-control-allow-origin')
  return expectStatus(res, 200) ?? (allowed === origin ? null : `allow-origin is "${allowed}"`)
})

await check('wrong key -> 401', async () =>
  expectStatus(await fetch(`${api}/sessions/${zero}/messages`, { headers: { 'X-API-Key': 'wrong-key' } }), 401),
)

if (key) {
  await check('right key -> 200 (history)', async () =>
    expectStatus(await fetch(`${api}/sessions/${zero}/messages`, { headers: { 'X-API-Key': key } }), 200),
  )
  await check('GET /documents -> 200', async () =>
    expectStatus(await fetch(`${api}/documents?owner_id=${randomUUID()}`, { headers: { 'X-API-Key': key } }), 200),
  )
} else {
  console.log('FAIL  SMOKE_KEY is not set (checks 3 and 4 need it)')
  failed = true
}

process.exit(failed ? 1 : 0)
