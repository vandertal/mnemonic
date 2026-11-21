import { ArrowLeft, Layers, Play, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { EmptyState } from '@/components/empty-state'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { deleteDeck, loadDecks, type Deck } from '@/features/flashcards/decks'
import { Review } from '@/features/flashcards/review'

const PAGE_SIZE = 6

function DeckView({ deck, onBack, onDelete }: { deck: Deck; onBack: () => void; onDelete: () => void }) {
  const { t } = useTranslation()
  const [reviewing, setReviewing] = useState(false)
  if (reviewing) return <Review deck={deck} onExit={() => setReviewing(false)} />
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft className="size-4" />
          {t('flashcards.back')}
        </Button>
        <div className="ml-auto flex gap-2">
          <Button variant="destructive" size="sm" onClick={onDelete}>
            <Trash2 className="size-4" />
            {t('flashcards.deleteDeck')}
          </Button>
          <Button size="sm" onClick={() => setReviewing(true)}>
            <Play className="size-4" />
            {t('flashcards.review')}
          </Button>
        </div>
      </div>
      <h2 className="text-base font-semibold break-words">{deck.question}</h2>
      <ul className="grid gap-3 sm:grid-cols-2">
        {deck.cards.map((c, i) => (
          <li key={i}>
            <Card className="h-full space-y-2 p-4">
              <p className="text-sm font-medium">{c.question}</p>
              <p className="border-t pt-2 text-sm text-muted-foreground">{c.answer}</p>
            </Card>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function FlashcardsPage() {
  const { t, i18n } = useTranslation()
  const [decks, setDecks] = useState(loadDecks) // read once per visit: decks are created on the chat page
  const [shown, setShown] = useState(PAGE_SIZE)
  const [openId, setOpenId] = useState<string | null>(null)
  const [confirm, setConfirm] = useState(false)
  const open = decks.find((d) => d.id === openId)
  const fmt = new Intl.DateTimeFormat(i18n.language, { dateStyle: 'medium' })

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      <div className="mx-auto max-w-3xl space-y-5">
        {!open && (
          <div>
            <h1 className="text-xl font-semibold tracking-tight">{t('nav.flashcards')}</h1>
            <p className="mt-1 text-sm text-muted-foreground">{t('flashcards.subtitle')}</p>
          </div>
        )}

        {open ? (
          <DeckView deck={open} onBack={() => setOpenId(null)} onDelete={() => setConfirm(true)} />
        ) : decks.length === 0 ? (
          <EmptyState icon={Layers} title={t('flashcards.emptyTitle')} text={t('flashcards.emptyText')} />
        ) : (
          <>
            <ul className="grid gap-3 sm:grid-cols-2">
              {decks.slice(0, shown).map((d) => (
                <li key={d.id}>
                  <button
                    type="button"
                    onClick={() => setOpenId(d.id)}
                    className="h-full w-full cursor-pointer rounded-lg border bg-card p-4 text-left shadow-sm transition-colors hover:bg-muted active:translate-y-px"
                  >
                    <span className="line-clamp-2 block text-sm font-medium">{d.question}</span>
                    <span className="mt-2 block text-xs text-muted-foreground">
                      {t('flashcards.cards', { count: d.cards.length })} · {fmt.format(d.createdAt)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            {shown < decks.length && (
              <div className="flex justify-center">
                <Button variant="outline" onClick={() => setShown((n) => n + PAGE_SIZE)}>
                  {t('flashcards.loadMore', { left: decks.length - shown })}
                </Button>
              </div>
            )}
          </>
        )}
      </div>

      <ConfirmDialog
        open={confirm}
        title={t('flashcards.confirmTitle')}
        description={t('flashcards.confirmText')}
        confirmLabel={t('flashcards.deleteDeck')}
        onCancel={() => setConfirm(false)}
        onConfirm={() => {
          if (openId) deleteDeck(openId)
          setDecks(loadDecks())
          setOpenId(null)
          setConfirm(false)
        }}
      />
    </div>
  )
}
