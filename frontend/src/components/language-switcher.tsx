import { useTranslation } from 'react-i18next'
import { LANGUAGES, type Language } from '@/i18n'
import { Segmented } from './segmented'

export function LanguageSwitcher() {
  const { t, i18n } = useTranslation()
  return (
    <Segmented
      value={(i18n.resolvedLanguage as Language) ?? 'en'}
      onChange={(lng) => void i18n.changeLanguage(lng)}
      label={t('settings.language')}
      options={LANGUAGES.map((l) => ({ value: l, label: l.toUpperCase() }))}
    />
  )
}
