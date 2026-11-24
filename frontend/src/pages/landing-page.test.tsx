import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { beforeAll, describe, expect, it, vi } from 'vitest'

// src/i18n touches `document` when it is imported; there is no DOM in the Node test environment.
vi.hoisted(() => {
  const g = globalThis as Record<string, unknown>
  g.document ??= { documentElement: { lang: '', classList: { toggle() {} } }, querySelector: () => null }
})
// The theme provider needs matchMedia; the landing page only needs the toggle to render.
vi.mock('@/lib/theme', () => ({ useTheme: () => ({ theme: 'light', setTheme() {} }) }))

import i18n from '@/i18n'
import LandingPage from './landing-page'
import pageSource from './landing-page.tsx?raw'
import mockSource from '@/features/landing/chat-mock.tsx?raw'

const html = (lang: 'en' | 'uk') => {
  void i18n.changeLanguage(lang)
  return renderToStaticMarkup(
    <MemoryRouter>
      <LandingPage />
    </MemoryRouter>,
  )
}

const count = (haystack: string, needle: RegExp) => (haystack.match(needle) ?? []).length

describe.each(['en', 'uk'] as const)('landing page (%s)', (lang) => {
  let out = ''
  beforeAll(() => {
    out = html(lang)
  })

  it('has one h1: the hero sentence in the page language', () => {
    expect(count(out, /<h1[ >]/g)).toBe(1)
    expect(out).toContain(i18n.getFixedT(lang)('landing.heroTitle'))
  })

  it('has one primary "Try it" button to /register and a secondary "Log in" to /login', () => {
    const t = i18n.getFixedT(lang)
    expect(out).toMatch(new RegExp(`<a[^>]*href="/register"[^>]*>${t('landing.tryIt')}`))
    expect(out).toMatch(new RegExp(`<a[^>]*href="/login"[^>]*>${t('landing.login')}</a>`))
  })

  it('has the landmarks: banner, navigation, main, contentinfo, and a skip link to #main', () => {
    expect(out).toContain('<header')
    expect(out).toContain('<nav')
    expect(out).toContain('<main id="main"')
    expect(out).toContain('<footer')
    expect(out).toContain('href="#main"')
  })

  it('shows 3 steps and 3 feature cards, each with its own heading', () => {
    expect(count(out, /<ol[ >]/g)).toBe(1)
    const steps = out.slice(out.indexOf('<ol'), out.indexOf('</ol>'))
    expect(count(steps, /<li[ >]/g)).toBe(3)
    expect(count(steps, /<h3[ >]/g)).toBe(3)
    const feats = out.slice(out.indexOf('aria-labelledby="features-title"'))
    expect(count(feats.slice(0, feats.indexOf('</ul>')), /<h3[ >]/g)).toBe(3)
  })

  it('draws the chat mock with citation chips, as one labelled image', () => {
    const t = i18n.getFixedT(lang)
    expect(out).toContain(`role="img" aria-label="${t('landing.mockLabel')}"`)
    expect(out).toContain(t('landing.mockQuestion'))
    expect(out).toContain('CORSMiddleware') // identifiers are set apart as <code>
    expect(out).toMatch(/<code[^>]*>CORSMiddleware<\/code>/)
  })

  it('has a privacy note and a footer link to the GitHub repository', () => {
    expect(out).toContain(i18n.getFixedT(lang)('landing.privacyTitle'))
    expect(out).toMatch(/<a[^>]*href="https:\/\/github\.com\/vandertal\/mnemonic"[^>]*rel="noopener noreferrer"/)
  })

  it('renders no missing translation keys', () => {
    expect(out).not.toMatch(/landing\.[a-zA-Z0-9]+/)
  })

  it('never injects raw HTML', () => {
    expect(out).not.toContain('dangerouslySetInnerHTML')
  })
})

describe('landing sources', () => {
  it('do not use dangerouslySetInnerHTML', () => {
    for (const source of [pageSource, mockSource]) expect(source).not.toContain('dangerouslySetInnerHTML')
  })
})
