export interface SseMessage {
  event: string // "message" when the server sent no `event:` line
  data: string
}

/**
 * Parse a Server-Sent Events byte stream.
 * Bytes arrive in arbitrary pieces: a piece can end in the middle of a line, or even in the middle of
 * a UTF-8 character. So we decode with {stream: true}, keep a buffer, and cut it only at the blank
 * line that ends an event.
 */
export async function* parseSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseMessage> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      // Normalise line endings, then split complete events off the front of the buffer.
      buffer = buffer.replace(/\r\n?/g, '\n')
      let end: number
      while ((end = buffer.indexOf('\n\n')) !== -1) {
        const block = buffer.slice(0, end)
        buffer = buffer.slice(end + 2)
        const msg = parseBlock(block)
        if (msg) yield msg
      }
    }
    buffer += decoder.decode()
    const tail = parseBlock(buffer.replace(/\r\n?/g, '\n').trim())
    if (tail) yield tail
  } finally {
    // Runs when the consumer stops early (Stop button): cancel closes the HTTP connection.
    await reader.cancel().catch(() => {})
  }
}

function parseBlock(block: string): SseMessage | null {
  let event = 'message'
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (!line || line.startsWith(':')) continue // blank or comment (keep-alive)
    const i = line.indexOf(':')
    const field = i === -1 ? line : line.slice(0, i)
    const val = i === -1 ? '' : line.slice(i + 1).replace(/^ /, '')
    if (field === 'event') event = val
    else if (field === 'data') data.push(val)
  }
  return data.length ? { event, data: data.join('\n') } : null
}
