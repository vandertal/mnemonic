import { apiJson } from './client'
import type { Explanation, Ranker, SearchHit, SearchMode } from './types'

export const MAX_QUERY = 200

export interface SearchParams {
  q: string
  ranker: Ranker
  mode: SearchMode
}

export const searchChunks = (p: SearchParams, signal?: AbortSignal) =>
  apiJson<SearchHit[]>(`/search?${new URLSearchParams({ ...p, limit: '10' })}`, { signal })

export const explainHit = (p: Pick<SearchParams, 'q' | 'ranker'>, chunkId: number) =>
  apiJson<Explanation>(`/search/explain?${new URLSearchParams({ ...p, chunk_id: String(chunkId) })}`)
