// Runs before `npm run dev`. Warns (never fails) when the API URL is missing or local.
import { readEnv } from './env.mjs'

const url = readEnv().VITE_API_URL?.trim()
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
