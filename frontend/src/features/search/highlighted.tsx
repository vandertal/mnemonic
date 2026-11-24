import { renderHighlights } from './highlights'

/** Snippet text with matched words in <mark>. Segments are React text nodes: markup stays text. */
export function Highlighted({ text, ranges }: { text: string; ranges: ReadonlyArray<readonly [number, number]> }) {
  return (
    <>
      {renderHighlights(text, ranges).map((seg, i) =>
        seg.mark ? (
          <mark key={i} className="rounded-sm bg-accent-soft px-0.5 text-foreground">
            {seg.text}
          </mark>
        ) : (
          <span key={i}>{seg.text}</span>
        ),
      )}
    </>
  )
}
