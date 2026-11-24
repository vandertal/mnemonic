import { Search, X } from 'lucide-react'
import { useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { MAX_QUERY } from '@/api/search'
import { ApiError, RateLimitError } from '@/api/errors'
import type { Ranker, SearchMode } from '@/api/types'
import { EmptyState } from '@/components/empty-state'
import { Segmented } from '@/components/segmented'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { ResultCard } from '@/features/search/result-card'
import { MIN_QUERY, normalizeQuery, useDebounced, useSearch } from '@/features/search/use-search'
import { describeError } from '@/lib/errors'

export default function SearchPage() {
  const { t } = useTranslation()
  const [input, setInput] = useState('')
  const [ranker, setRanker] = useState<Ranker>('bm25')
  const [mode, setMode] = useState<SearchMode>('all')
  const debounced = useDebounced(input)
  const q = normalizeQuery(debounced)
  const search = useSearch({ q, ranker, mode })

  // `idle` follows the live input (so clearing is instant); the request follows the debounced value.
  const idle = Array.from(normalizeQuery(input)).length < MIN_QUERY
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') setInput('')
  }

  let body
  if (idle) {
    body = <EmptyState icon={Search} title={t('search.idleTitle')} text={t('search.idleHint', { min: MIN_QUERY })} />
  } else if (search.isError) {
    const e = search.error
    const message =
      e instanceof RateLimitError
        ? t('search.rateLimited')
        : e instanceof ApiError && e.status === 503
          ? t('search.indexBuilding')
          : describeError(e)
    body = (
      <div role="alert" className="flex flex-col items-center gap-3 py-8 text-center text-sm text-muted-foreground">
        {message}
        <Button variant="outline" size="sm" onClick={() => void search.refetch()}>
          {t('chat.retry')}
        </Button>
      </div>
    )
  } else if (search.isPending || !search.data) {
    body = (
      <div className="space-y-2" role="status" aria-label={t('search.searching')}>
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    )
  } else if (search.data.length === 0) {
    body = <EmptyState icon={Search} title={t('search.emptyTitle')} text={t('search.emptyTip')} />
  } else {
    body = (
      <>
        <p className="text-xs text-muted-foreground" role="status">
          {t('search.count', { count: search.data.length })}
        </p>
        <ul className="space-y-2" aria-label={t('search.results')}>
          {search.data.map((hit) => (
            <ResultCard key={hit.chunk_id} hit={hit} q={q} ranker={ranker} />
          ))}
        </ul>
      </>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      <div className="mx-auto max-w-3xl space-y-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{t('nav.search')}</h1>
          <p className="text-sm text-muted-foreground">{t('search.subtitle')}</p>
        </div>

        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            autoFocus
            type="search"
            value={input}
            maxLength={MAX_QUERY}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKey}
            placeholder={t('search.placeholder')}
            aria-label={t('search.label')}
            className="pr-10 pl-9"
          />
          {input && (
            <button
              type="button"
              onClick={() => setInput('')}
              aria-label={t('search.clear')}
              className="absolute top-1/2 right-2 grid size-6 -translate-y-1/2 cursor-pointer place-items-center rounded text-muted-foreground hover:text-foreground"
            >
              <X className="size-4" />
            </button>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Segmented
            label={t('search.ranker')}
            value={ranker}
            onChange={setRanker}
            options={[
              { value: 'bm25', label: 'BM25' },
              { value: 'tfidf', label: 'TF-IDF' },
            ]}
          />
          <Segmented
            label={t('search.mode')}
            value={mode}
            onChange={setMode}
            options={[
              { value: 'all', label: t('search.modeAll') },
              { value: 'any', label: t('search.modeAny') },
            ]}
          />
        </div>

        {body}
      </div>
    </div>
  )
}
