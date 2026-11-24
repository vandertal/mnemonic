import { ArrowUp, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

/** A quiet one-line pointer to the "Make flashcards" button right above it. */
export function CardsHint({ onDismiss }: { onDismiss: () => void }) {
  const { t } = useTranslation()
  return (
    <div
      role="note"
      className="-ml-0.5 flex w-fit max-w-full items-center gap-2 rounded-full border bg-accent-soft py-1 pr-1 pl-3 text-xs text-foreground"
    >
      <ArrowUp className="size-3.5 shrink-0 text-accent" aria-hidden="true" />
      <span>{t('onboarding.cardsHint')}</span>
      <button
        type="button"
        onClick={onDismiss}
        aria-label={t('onboarding.dismiss')}
        className="grid size-6 shrink-0 cursor-pointer place-items-center rounded-full text-muted-foreground hover:bg-background hover:text-foreground"
      >
        <X className="size-3.5" />
      </button>
    </div>
  )
}
