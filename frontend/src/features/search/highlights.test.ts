import { describe, expect, it } from 'vitest'
import { renderHighlights } from './highlights'

const plain = (text: string) => ({ text, mark: false })
const mark = (text: string) => ({ text, mark: true })

describe('renderHighlights', () => {
  it('returns one plain segment when there are no ranges', () => {
    expect(renderHighlights('hello world', [])).toEqual([plain('hello world')])
  })

  it('returns nothing for empty text', () => {
    expect(renderHighlights('', [[0, 3]])).toEqual([])
  })

  it('marks one range', () => {
    expect(renderHighlights('use Depends here', [[4, 11]])).toEqual([plain('use '), mark('Depends'), plain(' here')])
  })

  it('marks a range at the very start and at the very end', () => {
    expect(renderHighlights('abcdef', [[0, 2], [4, 6]])).toEqual([mark('ab'), plain('cd'), mark('ef')])
  })

  it('merges adjacent ranges', () => {
    expect(renderHighlights('abcdef', [[1, 3], [3, 5]])).toEqual([plain('a'), mark('bcde'), plain('f')])
  })

  it('merges overlapping ranges, whatever the input order', () => {
    expect(renderHighlights('abcdefgh', [[4, 7], [2, 5]])).toEqual([plain('ab'), mark('cdefg'), plain('h')])
  })

  it('merges a range that sits inside another one', () => {
    expect(renderHighlights('abcdefgh', [[1, 7], [2, 3]])).toEqual([plain('a'), mark('bcdefg'), plain('h')])
  })

  it('clamps ranges that go past the end or before the start', () => {
    expect(renderHighlights('abcd', [[2, 99]])).toEqual([plain('ab'), mark('cd')])
    expect(renderHighlights('abcd', [[-5, 2]])).toEqual([mark('ab'), plain('cd')])
  })

  it('drops ranges that are fully outside, empty or inverted', () => {
    expect(renderHighlights('abcd', [[10, 20], [2, 2], [3, 1], [Number.NaN, 2]])).toEqual([plain('abcd')])
  })

  it('counts code points, not UTF-16 units: an emoji before the match', () => {
    // Python offsets for "🙂 Depends": the emoji is ONE code point, so "Depends" is [2, 9).
    // Slicing the JS string with those numbers would cut "🙂 Depe" -> wrong.
    expect(renderHighlights('🙂 Depends', [[2, 9]])).toEqual([plain('🙂 '), mark('Depends')])
  })

  it('never splits a surrogate pair', () => {
    expect(renderHighlights('a😀b', [[1, 2]])).toEqual([plain('a'), mark('😀'), plain('b')])
  })

  it('handles Ukrainian text', () => {
    expect(renderHighlights('Залежності в FastAPI', [[0, 10]])).toEqual([mark('Залежності'), plain(' в FastAPI')])
  })

  it('treats markup as plain text', () => {
    const [first] = renderHighlights('<script>alert(1)</script>', [[1, 7]])
    expect(first).toEqual(plain('<'))
    const all = renderHighlights('<script>alert(1)</script>', [[1, 7]])
    expect(all.map((s) => s.text).join('')).toBe('<script>alert(1)</script>')
    expect(all[1]).toEqual(mark('script'))
  })
})
