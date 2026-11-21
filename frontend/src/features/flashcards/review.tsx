import { ArrowLeft, ArrowRight, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { Deck } from './decks'

/** Flip-to-reveal review. Keys: ← → move, Space flips. */
export function Review({ deck, onExit }: { deck: Deck; onExit: () => void }) {
  const { t } = useTranslation()
  const [index, setIndex] = useState(0)
  const [flipped, setFlipped] = useState(false)
  const total = deck.cards.length
  const card = deck.cards[index]

  const go = useCallback(
    (delta: number) => {
      setIndex((i) => Math.min(total - 1, Math.max(0, i + delta)))
      setFlipped(false)
    },
    [total],
  )

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      if (target.closest('input, textarea, select')) return
      if (e.key === 'ArrowRight') go(1)
      else if (e.key === 'ArrowLeft') go(-1)
      else if (e.key === ' ' && !target.closest('button, a')) {
        e.preventDefault() // do not scroll the page
        setFlipped((f) => !f)
      } else if (e.key === 'Escape') onExit()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [go, onExit])

  return (
    <div className="mx-auto flex w-full max-w-xl flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <p className="min-w-0 truncate text-sm text-muted-foreground">{deck.question}</p>
        <Button variant="ghost" size="icon-sm" onClick={onExit} aria-label={t('flashcards.exit')}>
          <X className="size-4" />
        </Button>
      </div>

      <div
        role="progressbar"
        aria-valuemin={1}
        aria-valuemax={total}
        aria-valuenow={index + 1}
        aria-label={t('flashcards.progress', { current: index + 1, total })}
        className="h-1.5 overflow-hidden rounded-full bg-muted"
      >
        <div className="h-full bg-accent transition-[width]" style={{ width: `${((index + 1) / total) * 100}%` }} />
      </div>

      <div
        role="button"
        tabIndex={0}
        aria-pressed={flipped}
        onClick={() => setFlipped((f) => !f)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') setFlipped((f) => !f)
        }}
        className={cn(
          'flex min-h-56 cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border p-6 text-center shadow-sm transition-colors',
          flipped ? 'bg-accent-soft' : 'bg-card',
        )}
      >
        <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          {flipped ? t('flashcards.answer') : t('flashcards.question')}
        </span>
        <p className="text-lg leading-relaxed break-words">{flipped ? card.answer : card.question}</p>
        {!flipped && <span className="text-xs text-muted-foreground">{t('flashcards.flipHint')}</span>}
      </div>

      <div className="flex items-center justify-between">
        <Button variant="outline" onClick={() => go(-1)} disabled={index === 0}>
          <ArrowLeft className="size-4" />
          {t('flashcards.prev')}
        </Button>
        <span className="text-xs text-muted-foreground sm:text-sm" aria-live="polite">
          {t('flashcards.progress', { current: index + 1, total })}
        </span>
        <Button variant="outline" onClick={() => go(1)} disabled={index === total - 1}>
          {t('flashcards.next')}
          <ArrowRight className="size-4" />
        </Button>
      </div>
    </div>
  )
}
