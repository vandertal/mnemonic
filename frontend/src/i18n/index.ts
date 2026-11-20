import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import { readStored, writeStored } from '@/lib/storage'
import en from './en.json'
import uk from './uk.json'

export const LANGUAGES = ['uk', 'en'] as const
export type Language = (typeof LANGUAGES)[number]

function initialLanguage(): Language {
  const saved = readStored('lang')
  if (saved === 'uk' || saved === 'en') return saved
  // First visit: follow the browser. Ukrainian gets uk, everything else en.
  return /^uk/i.test(navigator.language) ? 'uk' : 'en'
}

void i18n.use(initReactI18next).init({
  resources: { uk: { translation: uk }, en: { translation: en } },
  lng: initialLanguage(),
  fallbackLng: 'en',
  interpolation: { escapeValue: false }, // React already escapes
})

document.documentElement.lang = i18n.language
i18n.on('languageChanged', (lng) => {
  writeStored('lang', lng)
  document.documentElement.lang = lng
})

export default i18n
