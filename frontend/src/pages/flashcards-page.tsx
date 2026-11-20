import { Layers } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { EmptyState } from '@/components/empty-state'

export default function FlashcardsPage() {
  const { t } = useTranslation()
  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      <h1 className="mx-auto max-w-3xl text-xl font-semibold tracking-tight">{t('nav.flashcards')}</h1>
      <EmptyState icon={Layers} title={t('flashcards.emptyTitle')} text={t('flashcards.emptyText')} />
    </div>
  )
}
