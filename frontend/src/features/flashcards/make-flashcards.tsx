import { useMutation } from '@tanstack/react-query'
import { Layers, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { createFlashcards } from '@/api/chat'
import { Button } from '@/components/ui/button'
import { useCurrentUser } from '@/lib/auth'
import { toastError } from '@/lib/errors'
import { saveDeck } from './decks'

/** "Make flashcards" under a finished answer: POST /flashcards, then store the deck in this browser. */
export function MakeFlashcardsButton({
  sessionId,
  messageId,
  question,
  onMake,
}: {
  sessionId: string
  messageId: number
  question: string
  /** Called when the user starts making cards (the onboarding hint is then redundant). */
  onMake?: () => void
}) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const user = useCurrentUser()
  const make = useMutation({
    mutationFn: () => createFlashcards(sessionId, messageId),
    onSuccess: (set) => {
      saveDeck(user.id, { id: `${sessionId}:${messageId}`, question, createdAt: Date.now(), cards: set.cards })
      toast.success(t('flashcards.created', { count: set.cards.length }), {
        action: { label: t('flashcards.open'), onClick: () => navigate('/flashcards') },
      })
    },
    onError: toastError,
  })
  return (
    <Button variant="ghost" size="sm" disabled={make.isPending} onClick={() => {
        onMake?.()
        make.mutate()
      }}>
      {make.isPending ? <Loader2 className="size-4 animate-spin" /> : <Layers className="size-4" />}
      {make.isPending ? t('flashcards.making') : t('flashcards.make')}
    </Button>
  )
}
