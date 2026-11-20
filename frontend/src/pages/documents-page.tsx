import { FileText, Loader2, Trash2, Upload } from 'lucide-react'
import { useRef, useState, type DragEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { EmptyState } from '@/components/empty-state'
import { Button } from '@/components/ui/button'
import { Card, Skeleton } from '@/components/ui/card'
import { useDocuments, useDeleteDocument, useUploadDocument } from '@/features/documents/use-documents'
import { ALLOWED_EXTENSIONS, MAX_DOCUMENTS, MAX_UPLOAD_MB, validateFile, type FileProblem } from '@/features/documents/validate'
import { cn } from '@/lib/utils'
import type { DocumentInfo } from '@/api/types'

function Dropzone({ count, onProblem }: { count: number; onProblem: (p: FileProblem | null) => void }) {
  const { t } = useTranslation()
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const upload = useUploadDocument()

  const take = (files: FileList | null) => {
    const file = files?.[0]
    if (!file) return
    const problem = validateFile(file, count)
    onProblem(problem)
    if (!problem) upload.mutate(file)
  }
  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setOver(false)
    if (!upload.isPending) take(e.dataTransfer.files)
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
      className={cn(
        'flex flex-col items-center gap-3 rounded-lg border-2 border-dashed p-6 text-center transition-colors',
        over ? 'border-accent bg-accent-soft' : 'bg-card',
      )}
    >
      {upload.isPending ? (
        <div role="status" className="flex flex-col items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-6 animate-spin text-accent" />
          {t('documents.uploading')}
        </div>
      ) : (
        <>
          <Upload className="size-6 text-accent" />
          <p className="text-sm text-muted-foreground">{t('documents.drop')}</p>
          <Button onClick={() => input.current?.click()}>{t('documents.choose')}</Button>
          <p className="text-xs text-muted-foreground">
            {t('documents.hint', { types: ALLOWED_EXTENSIONS.join(', '), mb: MAX_UPLOAD_MB, max: MAX_DOCUMENTS })}
          </p>
        </>
      )}
      <input
        ref={input}
        type="file"
        hidden
        accept={ALLOWED_EXTENSIONS.join(',')}
        onChange={(e) => {
          take(e.target.files)
          e.target.value = '' // so choosing the same file again fires change
        }}
      />
    </div>
  )
}

function DocumentCard({ doc, onDelete }: { doc: DocumentInfo; onDelete: () => void }) {
  const { t, i18n } = useTranslation()
  const date = new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium' }).format(new Date(doc.created_at))
  return (
    <Card className="flex items-center gap-3 p-3">
      <div className="grid size-10 shrink-0 place-items-center rounded-md bg-accent-soft text-accent">
        <FileText className="size-5" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{doc.filename}</p>
        <p className="text-xs text-muted-foreground">
          {t('documents.chunks', { count: doc.chunks })} · {date}
        </p>
      </div>
      <Button variant="ghost" size="icon-sm" onClick={onDelete} aria-label={t('documents.delete', { name: doc.filename })}>
        <Trash2 className="size-4" />
      </Button>
    </Card>
  )
}

export default function DocumentsPage() {
  const { t } = useTranslation()
  const { data, isPending, isError, refetch, isRefetching } = useDocuments()
  const remove = useDeleteDocument()
  const [problem, setProblem] = useState<FileProblem | null>(null)
  const [toDelete, setToDelete] = useState<DocumentInfo | null>(null)
  const docs = data ?? []

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      <div className="mx-auto max-w-3xl space-y-5">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">{t('nav.documents')}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t('documents.subtitle')}</p>
        </div>

        <div>
          <Dropzone count={docs.length} onProblem={setProblem} />
          {problem && (
            <p role="alert" className="mt-2 text-sm text-destructive">
              {t(problem.key, problem.params ?? {})}
            </p>
          )}
        </div>

        {isPending ? (
          <div className="space-y-2" role="status" aria-label={t('documents.loading')}>
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-[66px] w-full" />
            ))}
          </div>
        ) : isError ? (
          <div className="flex flex-col items-center gap-3 py-8 text-center">
            <p className="text-sm text-muted-foreground">{t('documents.loadFailed')}</p>
            <Button variant="outline" size="sm" disabled={isRefetching} onClick={() => void refetch()}>
              {t('chat.retry')}
            </Button>
          </div>
        ) : docs.length === 0 ? (
          <EmptyState icon={FileText} title={t('documents.emptyTitle')} text={t('documents.emptyText')} />
        ) : (
          <ul className="space-y-2">
            {docs.map((d) => (
              <li key={d.id}>
                <DocumentCard doc={d} onDelete={() => setToDelete(d)} />
              </li>
            ))}
          </ul>
        )}
      </div>

      <ConfirmDialog
        open={!!toDelete}
        title={t('documents.confirmTitle')}
        description={t('documents.confirmText', { name: toDelete?.filename ?? '' })}
        confirmLabel={t('documents.deleteConfirm')}
        onCancel={() => setToDelete(null)}
        onConfirm={() => {
          if (toDelete) remove.mutate(toDelete.id)
          setToDelete(null)
        }}
      />
    </div>
  )
}
