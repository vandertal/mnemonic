import type { Source } from '@/api/types'

// The model cites chunk ids: [42] or [42, 43]. The reader should see 1, 2, 3 matching the cards.
const CITATION = /\[(\d+(?:\s*,\s*\d+)*)\]/g

/** Replace chunk ids in the text with the position of the source card ([42] -> [1]). */
export function renumberCitations(text: string, sources: Source[]): string {
  if (!sources.length) return text
  const position = new Map(sources.map((s, i) => [s.id, i + 1]))
  return text.replace(CITATION, (whole, group: string) => {
    const numbers = group
      .split(',')
      .map((id) => position.get(Number(id.trim())))
      .filter((n): n is number => n !== undefined)
    return numbers.length ? `[${numbers.join(', ')}]` : whole
  })
}

// The server's fixed refusal starts with this; the model is also told to refuse the same way.
export const isRefusal = (text: string) => /^\s*i don'?t know/i.test(text)

/** A short plain-text preview of a chunk for the source card. */
export function snippetOf(markdown: string, max = 160): string {
  const plain = markdown
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[#>*_`|]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  return plain.length > max ? `${plain.slice(0, max).trimEnd()}…` : plain
}
