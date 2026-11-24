import { useTranslation } from 'react-i18next'
import type { Ranker } from '@/api/types'
import { Skeleton } from '@/components/ui/card'
import { describeError } from '@/lib/errors'
import { useExplain } from './use-search'

const fmt = (n: number) => n.toFixed(2)

/** "Why this result?": the BM25 / TF-IDF arithmetic, one row per query term. Teaching mode. */
export function ExplainPanel({ q, ranker, chunkId }: { q: string; ranker: Ranker; chunkId: number }) {
  const { t } = useTranslation()
  const { data, error, isPending } = useExplain({ q, ranker }, chunkId, true)

  if (isPending) return <Skeleton className="h-24 w-full" role="status" aria-label={t('common.loading')} />
  if (error || !data) return <p className="text-sm text-muted-foreground">{describeError(error)}</p>

  const max = Math.max(...data.terms.map((x) => x.contribution), Number.EPSILON)
  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[30rem] text-left text-xs">
          <caption className="sr-only">{t('search.explainTable')}</caption>
          <thead className="text-muted-foreground">
            <tr>
              <th scope="col" className="py-1 pr-3 font-medium">{t('search.term')}</th>
              <th scope="col" className="px-2 py-1 text-right font-medium">tf</th>
              <th scope="col" className="px-2 py-1 text-right font-medium">df</th>
              <th scope="col" className="px-2 py-1 text-right font-medium">idf</th>
              <th scope="col" className="px-2 py-1 text-right font-medium">{t('search.docLength')}</th>
              <th scope="col" className="py-1 pl-3 font-medium">{t('search.contribution')}</th>
            </tr>
          </thead>
          <tbody>
            {data.terms.map((x) => (
              <tr key={x.term} className="border-t">
                <th scope="row" className="py-1 pr-3 font-mono font-medium">{x.term}</th>
                <td className="px-2 py-1 text-right tabular-nums">{x.tf}</td>
                <td className="px-2 py-1 text-right tabular-nums">{x.df}</td>
                <td className="px-2 py-1 text-right tabular-nums">{fmt(x.idf)}</td>
                <td className="px-2 py-1 text-right tabular-nums">{data.doc_length}</td>
                <td className="py-1 pl-3">
                  <span className="flex items-center gap-2">
                    <span className="h-2 w-24 overflow-hidden rounded-full bg-muted" aria-hidden="true">
                      <span className="block h-full rounded-full bg-accent" style={{ width: `${(x.contribution / max) * 100}%` }} />
                    </span>
                    <span className="tabular-nums">{fmt(x.contribution)}</span>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t font-semibold">
              <th scope="row" colSpan={5} className="py-1 pr-3 text-right">{t('search.total')}</th>
              <td className="py-1 pl-3 tabular-nums">{fmt(data.score)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      <p className="text-xs text-muted-foreground">
        {t(data.ranker === 'bm25' ? 'search.explainBm25' : 'search.explainTfidf', { n: data.n_docs })}
      </p>
    </div>
  )
}
