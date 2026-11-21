import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation } from 'react-router-dom'

const TITLE_KEYS: Record<string, string> = {
  '/access': 'access.title',
  '/chat': 'nav.chat',
  '/documents': 'nav.documents',
  '/flashcards': 'nav.flashcards',
  '/settings': 'nav.settings',
}

/** "Documents · Mnemonic": a descriptive tab title per route, re-evaluated when the language changes. */
export function usePageTitle() {
  const { t, i18n } = useTranslation()
  const { pathname } = useLocation()
  useEffect(() => {
    const key = TITLE_KEYS[pathname] ?? (pathname === '/' ? 'nav.chat' : 'notFound.title')
    document.title = `${t(key)} · ${t('app.name')}`
  }, [pathname, t, i18n.language])
}
