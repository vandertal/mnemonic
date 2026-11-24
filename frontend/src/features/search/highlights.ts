export interface Segment {
  text: string
  /** true: this part matched the query and is drawn inside <mark>. */
  mark: boolean
}

/**
 * Cut `text` into plain and highlighted segments.
 *
 * The API computes `[start, end)` offsets in Python, i.e. in Unicode CODE POINTS. A JavaScript
 * string is indexed in UTF-16 CODE UNITS, where an emoji takes two. Slicing the string with the raw
 * offsets would shift every highlight after an emoji, so the text is first split into code points
 * (`Array.from` iterates by code point) and the offsets index that array.
 *
 * Out-of-range offsets are clamped, empty or inverted ranges are dropped, ranges are sorted and
 * overlapping or touching ones are merged. Returns text only: the caller renders <mark> elements,
 * so nothing in the text can ever be interpreted as HTML.
 */
export function renderHighlights(text: string, ranges: ReadonlyArray<readonly [number, number]>): Segment[] {
  const points = Array.from(text)
  const n = points.length
  if (n === 0) return []

  const clean: [number, number][] = []
  for (const [a, b] of ranges) {
    if (!Number.isFinite(a) || !Number.isFinite(b)) continue
    const start = Math.max(0, Math.min(n, Math.trunc(a)))
    const end = Math.max(0, Math.min(n, Math.trunc(b)))
    if (end > start) clean.push([start, end])
  }
  clean.sort((x, y) => x[0] - y[0] || x[1] - y[1])

  const merged: [number, number][] = []
  for (const r of clean) {
    const last = merged[merged.length - 1]
    if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1])
    else merged.push([r[0], r[1]])
  }

  const out: Segment[] = []
  let pos = 0
  for (const [start, end] of merged) {
    if (start > pos) out.push({ text: points.slice(pos, start).join(''), mark: false })
    out.push({ text: points.slice(start, end).join(''), mark: true })
    pos = end
  }
  if (pos < n) out.push({ text: points.slice(pos).join(''), mark: false })
  return out
}
