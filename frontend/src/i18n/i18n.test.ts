import { describe, expect, it } from 'vitest'
import en from './en.json'
import uk from './uk.json'

/** Every key path of a nested JSON object, e.g. "chat.suggestions". */
function keys(obj: Record<string, unknown>, prefix = ''): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === 'object' && !Array.isArray(v)
      ? keys(v as Record<string, unknown>, `${prefix}${k}.`)
      : [`${prefix}${k}`],
  )
}

describe('translations', () => {
  it('uk and en have exactly the same keys (Ukrainian has extra plural forms: few, many)', () => {
    const base = (k: string) => k.replace(/_(zero|one|two|few|many|other)$/, '')
    const e = [...new Set(keys(en).map(base))]
    const u = [...new Set(keys(uk).map(base))]
    expect(e.filter((k) => !u.includes(k))).toEqual([]) // missing in uk
    expect(u.filter((k) => !e.includes(k))).toEqual([]) // missing in en
  })

  it('the onboarding example questions are the same count in both languages (3)', () => {
    expect(en.chat.suggestions).toHaveLength(3)
    expect(uk.chat.suggestions).toHaveLength(3)
  })

  it('every {{placeholder}} of an English string also exists in the Ukrainian one', () => {
    const flat = (o: Record<string, unknown>): Record<string, string> =>
      Object.fromEntries(
        keys(o)
          .map((k) => [k, k.split('.').reduce<unknown>((x, p) => (x as Record<string, unknown>)[p], o)] as const)
          .filter((entry): entry is readonly [string, string] => typeof entry[1] === 'string'),
      )
    const fe = flat(en)
    const fu = flat(uk)
    const vars = (s: string) => (s.match(/\{\{\w+\}\}/g) ?? []).sort().join()
    for (const k of Object.keys(fe)) expect(vars(fu[k] ?? ''), k).toBe(vars(fe[k]))
  })
})
