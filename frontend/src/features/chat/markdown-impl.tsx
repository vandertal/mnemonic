import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import { cn } from '@/lib/utils'
import { CITE_PREFIX } from './citations'

export interface CitationLinks {
  /** DOM id of the source card for citation number n (1-based). */
  idFor: (n: number) => string
  titleFor: (n: number) => string
}

function scrollToSource(id: string) {
  const el = document.getElementById(id)
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  el.focus({ preventScroll: true })
  el.setAttribute('data-flash', '')
  window.setTimeout(() => el.removeAttribute('data-flash'), 1600)
}

/** Model output is untrusted: react-markdown renders it as React elements and ignores raw HTML. */
export default function MarkdownImpl({
  children,
  className,
  citations,
}: {
  children: string
  className?: string
  citations?: CitationLinks
}) {
  const { t } = useTranslation()
  return (
    <div className={cn('markdown', className)}>
      <ReactMarkdown
        components={{
          a: ({ node: _node, href, children: label, ...props }) => {
            if (citations && href?.startsWith(CITE_PREFIX)) {
              const n = Number(href.slice(CITE_PREFIX.length))
              return (
                <a
                  href={`#${citations.idFor(n)}`}
                  title={citations.titleFor(n)}
                  aria-label={`${t('source.open', { n })}: ${citations.titleFor(n)}`}
                  onClick={(e) => {
                    e.preventDefault()
                    scrollToSource(citations.idFor(n))
                  }}
                  className="mx-0.5 inline-grid h-5 min-w-5 place-items-center rounded-md bg-accent-soft px-1 align-baseline text-xs font-semibold text-accent no-underline tabular-nums transition-colors hover:bg-accent hover:text-accent-foreground"
                >
                  {label}
                </a>
              )
            }
            return (
              <a href={href} {...props} target="_blank" rel="noopener noreferrer">
                {label}
              </a>
            )
          },
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
}
