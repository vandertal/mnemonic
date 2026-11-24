import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { Source } from '@/api/types'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/card'
import { snippetOf } from './citations'
import { Markdown } from './markdown'
import { useChunk } from './use-chunk'

/** What the dialog needs. `similarity` is optional: a search hit has a BM25 score, not a cosine match. */
export type SourceRef = Pick<Source, 'id' | 'file_path' | 'heading'> & { similarity?: number }

const titleOf = (s: SourceRef) => s.heading || s.file_path

function SourceDialogBody({ source }: { source: SourceRef }) {
  const { t } = useTranslation()
  const state = useChunk(source.id)
  return (
    <>
      <DialogTitle className="pr-8 text-base font-semibold">{titleOf(source)}</DialogTitle>
      <DialogDescription className="mt-1 text-xs text-muted-foreground">
        {source.file_path}
        {source.similarity !== undefined && ` · ${t('source.match', { percent: Math.round(source.similarity * 100) })}`}
      </DialogDescription>
      <div className="mt-4 text-sm">
        {state.status === 'loading' && (
          <div className="space-y-2" aria-label={t('source.loading')}>
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-5/6" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        )}
        {state.status === 'error' && <p className="text-muted-foreground">{t('source.failed')}</p>}
        {state.status === 'ready' && <Markdown>{state.chunk.content}</Markdown>}
      </div>
    </>
  )
}

/** The passage viewer, shared by chat citations and search results. */
export function SourceDialog({
  source,
  open,
  onOpenChange,
}: {
  source: SourceRef
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>{open && <SourceDialogBody source={source} />}</DialogContent>
    </Dialog>
  )
}

export function SourceCard({ source, index, domId }: { source: Source; index: number; domId?: string }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const state = useChunk(source.id)
  const snippet = state.status === 'ready' ? snippetOf(state.chunk.content) : null

  return (
    <>
      <button
        id={domId}
        type="button"
        onClick={() => setOpen(true)}
        aria-label={t('source.open', { n: index })}
        className="flex w-full cursor-pointer gap-3 rounded-lg border bg-card p-3 text-left shadow-sm transition-colors hover:bg-muted data-[flash]:ring-2 data-[flash]:ring-accent"
      >
        <span className="grid size-6 shrink-0 place-items-center rounded-md bg-accent-soft text-xs font-semibold text-accent">
          {index}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium">{titleOf(source)}</span>
          {snippet ? (
            <span className="mt-0.5 line-clamp-2 block text-xs text-muted-foreground">{snippet}</span>
          ) : state.status === 'loading' ? (
            <Skeleton className="mt-1.5 h-3 w-4/5" />
          ) : (
            <span className="mt-0.5 block truncate text-xs text-muted-foreground">{source.file_path}</span>
          )}
        </span>
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>{open && <SourceDialogBody source={source} />}</DialogContent>
      </Dialog>
    </>
  )
}
