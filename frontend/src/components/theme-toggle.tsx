import { Monitor, Moon, Sun } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useTheme, type Theme } from '@/lib/theme'
import { Segmented } from './segmented'

export function ThemeToggle() {
  const { t } = useTranslation()
  const { theme, setTheme } = useTheme()
  const items: { value: Theme; icon: typeof Sun; key: string }[] = [
    { value: 'light', icon: Sun, key: 'settings.themeLight' },
    { value: 'dark', icon: Moon, key: 'settings.themeDark' },
    { value: 'system', icon: Monitor, key: 'settings.themeSystem' },
  ]
  return (
    <Segmented
      value={theme}
      onChange={setTheme}
      label={t('settings.theme')}
      options={items.map(({ value, icon: Icon, key }) => ({
        value,
        ariaLabel: t(key),
        label: <Icon className="size-3.5" />,
      }))}
    />
  )
}
