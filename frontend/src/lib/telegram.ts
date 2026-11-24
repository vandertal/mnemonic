/**
 * The optional Telegram bot link. `VITE_TELEGRAM_BOT_URL` is baked in at build time; unset or
 * anything that is not an https://t.me/… link means "no bot": the link is hidden everywhere.
 * Read per call (not once at import) so a test can change the variable.
 */
export function telegramBotUrl(raw: string | undefined = import.meta.env.VITE_TELEGRAM_BOT_URL): string | null {
  const value = raw?.trim()
  if (!value) return null
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && url.hostname === 't.me' ? url.toString() : null
  } catch {
    return null
  }
}
