import { useEffect, useState } from 'react'
import { fetchChunk } from '@/api/chat'
import type { Chunk } from '@/api/types'

// One request per chunk: the card (snippet) and the dialog (full text) share the same promise.
const cache = new Map<number, Promise<Chunk>>()

function load(id: number): Promise<Chunk> {
  let p = cache.get(id)
  if (!p) {
    p = fetchChunk(id)
    cache.set(id, p)
    p.catch(() => cache.delete(id)) // a failure must not be remembered: the next try can succeed
  }
  return p
}

export type ChunkState = { status: 'loading' } | { status: 'error' } | { status: 'ready'; chunk: Chunk }

export function useChunk(id: number, enabled = true): ChunkState {
  const [result, setResult] = useState<{ id: number; state: ChunkState } | null>(null)

  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    load(id).then(
      (chunk) => !cancelled && setResult({ id, state: { status: 'ready', chunk } }),
      () => !cancelled && setResult({ id, state: { status: 'error' } }),
    )
    return () => {
      cancelled = true
    }
  }, [id, enabled])

  return result?.id === id ? result.state : { status: 'loading' }
}
