// Shared by check-env and smoke: env vars win, then frontend/.env. No dependencies.
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const envFile = join(dirname(fileURLToPath(import.meta.url)), '..', '.env')

export function readEnv() {
  const values = {}
  if (existsSync(envFile)) {
    for (const line of readFileSync(envFile, 'utf8').split(/\r?\n/)) {
      const m = /^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/.exec(line)
      if (m) values[m[1]] = m[2].replace(/^(['"])(.*)\1$/, '$2')
    }
  }
  return { ...values, ...process.env }
}
