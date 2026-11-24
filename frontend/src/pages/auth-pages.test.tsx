import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

vi.hoisted(() => {
  const g = globalThis as Record<string, unknown>
  g.document ??= { documentElement: { lang: '', classList: { toggle() {} } }, querySelector: () => null }
})
vi.mock('sonner', () => ({ toast: { error() {}, success() {} } }))
vi.mock('@/lib/theme', () => ({ useTheme: () => ({ theme: 'light', setTheme() {} }) }))
// The pages read the auth state: signed out, so the form is rendered (a signed-in user is redirected).
vi.mock('@/lib/auth', () => ({
  useAuth: () => ({ status: 'anonymous', login: vi.fn(), register: vi.fn() }),
}))

import i18n from '@/i18n'
import LoginPage from './login-page'
import RegisterPage from './register-page'

const render = (page: React.ReactElement, lang: 'en' | 'uk') => {
  void i18n.changeLanguage(lang)
  return renderToStaticMarkup(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>{page}</MemoryRouter>
    </QueryClientProvider>,
  )
}

describe.each([
  ['login', LoginPage],
  ['register', RegisterPage],
] as const)('%s screen', (_name, Page) => {
  it.each(['en', 'uk'] as const)('has a visible link back to the landing page (%s)', (lang) => {
    const html = render(<Page />, lang)
    expect(html).toMatch(/<a [^>]*href="\/"/)
    expect(html).toContain(i18n.getFixedT(lang)('auth.backHome')) // the accessible name
    expect(html).toContain('Mnemonic')
  })
})
