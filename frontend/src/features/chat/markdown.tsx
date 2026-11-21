import { lazy, Suspense } from 'react'
import { cn } from '@/lib/utils'
import type { CitationLinks } from './markdown-impl'

// react-markdown and its parser are the heaviest dependency; they load only when a message is shown.
const MarkdownImpl = lazy(() => import('./markdown-impl'))

export function Markdown(props: { children: string; className?: string; citations?: CitationLinks }) {
  return (
    // The fallback is the raw text in the same box, so the answer does not jump when the chunk arrives.
    <Suspense fallback={<div className={cn('markdown whitespace-pre-wrap', props.className)}>{props.children}</div>}>
      <MarkdownImpl {...props} />
    </Suspense>
  )
}
