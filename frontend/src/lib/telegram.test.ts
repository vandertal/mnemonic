import { describe, expect, it } from 'vitest'
import { telegramBotUrl } from './telegram'

describe('telegramBotUrl', () => {
  it('is null when the variable is unset or blank', () => {
    expect(telegramBotUrl(undefined)).toBeNull()
    expect(telegramBotUrl('')).toBeNull()
    expect(telegramBotUrl('   ')).toBeNull()
  })

  it('accepts an https://t.me link', () => {
    expect(telegramBotUrl('https://t.me/MnemonicStudyBot')).toBe('https://t.me/MnemonicStudyBot')
    expect(telegramBotUrl(' https://t.me/MnemonicStudyBot ')).toBe('https://t.me/MnemonicStudyBot')
  })

  it('rejects anything else, so a typo cannot put a foreign or script link on the page', () => {
    expect(telegramBotUrl('http://t.me/Bot')).toBeNull()
    expect(telegramBotUrl('https://evil.example/t.me/Bot')).toBeNull()
    expect(telegramBotUrl('https://t.me.evil.example/Bot')).toBeNull()
    expect(telegramBotUrl('javascript:alert(1)')).toBeNull()
    expect(telegramBotUrl('MnemonicStudyBot')).toBeNull()
  })
})
