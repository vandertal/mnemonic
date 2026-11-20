import ReactMarkdown from 'react-markdown'
import { cn } from '@/lib/utils'

/** Model output is untrusted: react-markdown renders it as React elements and ignores raw HTML. */
export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn('markdown', className)}>
      <ReactMarkdown
        components={{
          a: ({ node: _node, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  )
}
