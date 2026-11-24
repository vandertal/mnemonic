/** Same limit as the backend (`ChatRequest.message`, max_length=2000). */
export const MAX_QUESTION = 2000
/** Show the character counter from here on. */
export const COUNTER_FROM = 1800

// Lone surrogates (a broken emoji half) cannot be encoded as UTF-8: the server rejects them.
const LONE_SURROGATE = /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/g
// NUL cannot be stored by Postgres; other C0 controls (except tab and newline) are paste junk.
// eslint-disable-next-line no-control-regex
const CONTROL = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g

/**
 * What is really sent: junk characters removed, surrounding whitespace trimmed, cut to the limit
 * (never in the middle of an emoji). An empty result means "nothing to send".
 */
export function cleanQuestion(raw: string): string {
  const text = raw.replace(CONTROL, '').replace(LONE_SURROGATE, '').trim()
  if (text.length <= MAX_QUESTION) return text
  const cut = text.slice(0, MAX_QUESTION)
  return cut.replace(LONE_SURROGATE, '').trimEnd() // slicing may have split a surrogate pair
}
