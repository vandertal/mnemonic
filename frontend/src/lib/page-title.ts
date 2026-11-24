import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useLocation } from 'react-router-dom'

const TITLE_KEYS: Record<string, string> = {
  '/login': 'auth.loginTitle',
  '/register': 'auth.registerTitle',
  '/chat': 'nav.chat',
  '/search': 'nav.search',
  '/documents': 'nav.documents',
  '/flashcards': 'nav.flashcards',
  '/settings': 'nav.settings',
}

/** "Documents · Mnemonic": a descriptive tab title per route, re-evaluated when the language changes. */
export function usePageTitle() {
  const { t, i18n } = useTranslation()
  const { pathname } = useLocation()
  useEffect(() => {
    if (pathname === '/') {
      document.title = t('landing.metaTitle') // the landing page: a full sentence, no "· Mnemonic"
      return
    }
    const section = pathname.startsWith('/chat/') ? '/chat' : pathname
    const key = TITLE_KEYS[section] ?? 'notFound.title'
    document.title = `${t(key)} · ${t('app.name')}`
  }, [pathname, t, i18n.language])
}
