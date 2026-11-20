import { Calculator, Check, Copy, OctagonAlert, SearchX } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { isRefusal, renumberCitations } from './citations'
import { Markdown } from './markdown'
import { SourceCard } from './source-card'
import type { ChatMessage } from './use-chat'

function CopyButton({ text }: { text: string }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  const timer = useRef<number>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      timer.current = window.setTimeout(() => setCopied(false), 1500)
    } catch {
      toast.error(t('errors.generic'))
    }
  }
  return (
    <Button variant="ghost" size="icon-sm" onClick={copy} aria-label={copied ? t('chat.copied') : t('chat.copy')}>
      {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
    </Button>
  )
}

function UserMessage({ message }: { message: ChatMessage }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] rounded-2xl rounded-br-md bg-muted px-4 py-2.5 text-[15px] leading-relaxed break-words whitespace-pre-wrap">
        {message.content}
      </div>
    </div>
  )
}

function AssistantMessage({ message }: { message: ChatMessage }) {
  const { t } = useTranslation()
  const { content, status, sources, tools } = message
  const streaming = status === 'streaming'
  const refusal = !streaming && isRefusal(content)
  const text = streaming ? content : renumberCitations(content, sources)

  return (
    <div className="flex flex-col gap-3">
      {tools.map((tool, i) => (
        <div
          key={i}
          className="flex w-fit max-w-full items-center gap-2 rounded-md border bg-muted px-2.5 py-1 text-xs text-muted-foreground"
        >
          <Calculator className="size-3.5 shrink-0" />
          <span className="truncate">
            {t('chat.tool', { name: tool.name })}: {tool.result}
          </span>
        </div>
      ))}

      {streaming && !content ? (
        <div className="space-y-2.5 py-1" role="status" aria-label={t('chat.assistant')}>
          <Skeleton className="h-4 w-11/12" />
          <Skeleton className="h-4 w-4/5" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      ) : refusal ? (
        <div className="rounded-lg border border-warning-border bg-warning-soft p-4">
          <div className="mb-1.5 flex items-center gap-2 text-sm font-medium">
            <SearchX className="size-4" />
            {t('chat.dontKnow')}
          </div>
          <p className="text-sm text-muted-foreground">{content}</p>
        </div>
      ) : (
        content && <Markdown className={cn(streaming && 'streaming-caret')}>{text}</Markdown>
      )}

      {status === 'error' && (
        <div className="flex items-start gap-2 rounded-lg border border-destructive/40 p-3 text-sm text-destructive" role="alert">
          <OctagonAlert className="mt-0.5 size-4 shrink-0" />
          {message.error}
        </div>
      )}
      {status === 'stopped' && <p className="text-xs text-muted-foreground">{t('chat.stopped')}</p>}

      {sources.length > 0 && status !== 'streaming' && (
        <section aria-label={t('chat.sources')}>
          <h3 className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">{t('chat.sources')}</h3>
          <div className="grid gap-2 sm:grid-cols-2">
            {sources.map((s, i) => (
              <SourceCard key={s.id} source={s} index={i + 1} />
            ))}
          </div>
        </section>
      )}

      {!streaming && content && !refusal && (
        <div className="-ml-2 flex">
          <CopyButton text={text} />
        </div>
      )}
    </div>
  )
}

export function MessageView({ message }: { message: ChatMessage }) {
  return message.role === 'user' ? <UserMessage message={message} /> : <AssistantMessage message={message} />
}
