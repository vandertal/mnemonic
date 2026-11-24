import { Layers } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

// A hand-built, static picture of the real chat: a streamed answer with citation chips. Plain JSX,
// no image file (nothing to download, nothing that can shift the layout), and the colours come from
// the same tokens as the app, so it follows the light/dark theme by itself.

const CODE_TOKENS = /\b(CORSMiddleware|allow_origins)\b/g

/** The translated sentence with its identifiers set in a monospace chip. No HTML strings involved. */
function withCode(text: string): ReactNode[] {
  return text.split(CODE_TOKENS).map((part, i) =>
    i % 2 === 1 ? (
      <code key={i} className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">
        {part}
      </code>
    ) : (
      part
    ),
  )
}

/** Same look as the clickable [1] chip under a real answer. */
function Chip({ n }: { n: number }) {
  return (
    <span className="mx-0.5 inline-grid h-5 min-w-5 place-items-center rounded-md bg-accent-soft px-1 align-baseline text-xs font-semibold text-accent tabular-nums">
      {n}
    </span>
  )
}

function SourceRow({ n, title, file }: { n: number; title: string; file: string }) {
  return (
    <div className="flex min-w-0 gap-3 rounded-lg border bg-card p-2.5 shadow-sm">
      <span className="grid size-6 shrink-0 place-items-center rounded-md bg-accent-soft text-xs font-semibold text-accent">
        {n}
      </span>
      <span className="min-w-0">
        <span className="block truncate text-sm font-medium">{title}</span>
        <span className="block truncate text-xs text-muted-foreground">{file}</span>
      </span>
    </div>
  )
}

export function ChatMock() {
  const { t } = useTranslation()
  return (
    <div
      role="img"
      aria-label={t('landing.mockLabel')}
      className="overflow-hidden rounded-2xl border bg-card text-left shadow-md select-none"
    >
      <div aria-hidden="true">
        <div className="flex items-center gap-1.5 border-b bg-muted/60 px-4 py-2.5">
          <span className="size-2.5 rounded-full bg-border" />
          <span className="size-2.5 rounded-full bg-border" />
          <span className="size-2.5 rounded-full bg-border" />
          <span className="ml-3 text-xs font-medium text-muted-foreground">{t('app.name')}</span>
        </div>

        <div className="flex flex-col gap-4 p-4 sm:p-5">
          <div className="flex justify-end">
            <div className="max-w-[85%] rounded-2xl rounded-br-md bg-muted px-4 py-2.5 text-[15px] leading-relaxed">
              {t('landing.mockQuestion')}
            </div>
          </div>

          <p className="text-[15px] leading-relaxed">
            {withCode(t('landing.mockAnswer1'))}
            <Chip n={1} />. {withCode(t('landing.mockAnswer2'))}
            <Chip n={2} />
            <span className="ml-0.5 inline-block h-4 w-2 translate-y-0.5 animate-[caret_1s_steps(1)_infinite] rounded-sm bg-accent motion-reduce:animate-none" />
          </p>

          <div>
            <p className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
              {t('landing.mockSources')}
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              <SourceRow n={1} title="CORS (Cross-Origin Resource Sharing)" file="tutorial/cors.md" />
              <SourceRow n={2} title="Use CORSMiddleware" file="tutorial/cors.md" />
            </div>
          </div>

          <span className="inline-flex h-8 w-fit items-center gap-2 rounded-md px-3 text-sm font-medium text-foreground">
            <Layers className="size-4" />
            {t('landing.mockMake')}
          </span>
        </div>
      </div>
    </div>
  )
}
