import { describe, expect, it } from 'vitest'
import { MAX_QUESTION, cleanQuestion } from './question'

describe('cleanQuestion', () => {
  it('trims and keeps normal text, including Ukrainian, CJK and emoji', () => {
    expect(cleanQuestion('  Що таке CORS? 🤔 \n')).toBe('Що таке CORS? 🤔')
    expect(cleanQuestion('什么是 CORS')).toBe('什么是 CORS')
  })

  it('keeps newlines and tabs inside the text', () => {
    expect(cleanQuestion('line one\n\tline two')).toBe('line one\n\tline two')
  })

  it('removes NUL and other control characters that a paste can carry', () => {
    expect(cleanQuestion('a\u0000b\u0007c\u007f')).toBe('abc')
  })

  it('removes a lone surrogate but keeps a whole emoji', () => {
    expect(cleanQuestion('bad \ud800 text')).toBe('bad  text')
    expect(cleanQuestion('ok 🤔')).toBe('ok 🤔')
  })

  it('gives an empty string for blank or junk-only input (nothing to send)', () => {
    expect(cleanQuestion('   \n\t ')).toBe('')
    expect(cleanQuestion('\u0000\u0000')).toBe('')
  })

  it('cuts to the server limit, never in the middle of an emoji', () => {
    const long = 'x'.repeat(MAX_QUESTION - 1) + '🤔' // the emoji straddles the limit
    const out = cleanQuestion(long)
    expect(out.length).toBeLessThanOrEqual(MAX_QUESTION)
    expect(out).toBe('x'.repeat(MAX_QUESTION - 1))
    expect(cleanQuestion('y'.repeat(5000))).toHaveLength(MAX_QUESTION)
  })
})
