import { useEffect, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { explainHit, searchChunks, MAX_QUERY, type SearchParams } from '@/api/search'

export const MIN_QUERY = 2
const DEBOUNCE_MS = 250

/** The value, but only after it stopped changing for `ms`. */
export function useDebounced<T>(value: T, ms = DEBOUNCE_MS): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms)
    return () => clearTimeout(id)
  }, [value, ms])
  return debounced
}

/** Trim and cap like the server does; a query shorter than MIN_QUERY is "idle", not sent. */
export const normalizeQuery = (raw: string) => Array.from(raw.trim()).slice(0, MAX_QUERY).join('')

export function useSearch(params: SearchParams) {
  const q = normalizeQuery(params.q)
  return useQuery({
    queryKey: ['search', { ...params, q }],
    queryFn: ({ signal }) => searchChunks({ ...params, q }, signal),
    enabled: Array.from(q).length >= MIN_QUERY,
    placeholderData: keepPreviousData,
  })
}

export const useExplain = (params: Pick<SearchParams, 'q' | 'ranker'>, chunkId: number, enabled: boolean) =>
  useQuery({
    queryKey: ['search-explain', params, chunkId],
    queryFn: () => explainHit(params, chunkId),
    enabled,
  })
