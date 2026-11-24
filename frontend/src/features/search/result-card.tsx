import { ChevronDown } from 'lucide-react'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Ranker, SearchHit } from '@/api/types'
import { SourceDialog } from '@/features/chat/source-card'
import { cn } from '@/lib/utils'
import { ExplainPanel } from './explain-panel'
import { Highlighted } from './highlighted'

export function ResultCard({ hit, q, ranker }: { hit: SearchHit; q: string; ranker: Ranker }) {
  const { t } = useTranslation()
  const [viewing, setViewing] = useState(false)
  const [why, setWhy] = useState(false)
  const panelId = useId()

  return (
    <li className="rounded-lg border bg-card shadow-sm">
      {/* The viewer is the same dialog the chat citations use. */}
      <button
        type="button"
        onClick={() => setViewing(true)}
        className="block w-full cursor-pointer rounded-t-lg p-3 text-left transition-colors hover:bg-muted"
      >
        <span className="flex items-baseline justify-between gap-3">
          <span className="min-w-0 truncate text-sm font-medium">{hit.heading || hit.document}</span>
          <span className="shrink-0 text-xs text-muted-foreground tabular-nums" title={t('search.score')}>
            {hit.score.toFixed(2)}
          </span>
        </span>
        <span className="block truncate text-xs text-muted-foreground">{hit.document}</span>
        <span className="mt-1.5 line-clamp-3 block text-sm text-muted-foreground">
          <Highlighted text={hit.snippet.text} ranges={hit.snippet.highlights} />
        </span>
        {hit.matched_terms.length > 0 && (
          <span className="mt-2 flex flex-wrap gap-1.5">
            {hit.matched_terms.map((term) => (
              <span key={term} className="rounded-full bg-accent-soft px-2 py-0.5 font-mono text-[11px] text-accent">
                {term}
              </span>
            ))}
          </span>
        )}
      </button>

      <div className="border-t px-3 py-2">
        <button
          type="button"
          aria-expanded={why}
          aria-controls={panelId}
          onClick={() => setWhy((v) => !v)}
          className="flex cursor-pointer items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
        >
          <ChevronDown className={cn('size-3.5 transition-transform', why && 'rotate-180')} />
          {t('search.why')}
        </button>
        <div id={panelId} hidden={!why} className="mt-2">
          {why && <ExplainPanel q={q} ranker={ranker} chunkId={hit.chunk_id} />}
        </div>
      </div>

      <SourceDialog
        source={{ id: hit.chunk_id, file_path: hit.document, heading: hit.heading }}
        open={viewing}
        onOpenChange={setViewing}
      />
    </li>
  )
}
