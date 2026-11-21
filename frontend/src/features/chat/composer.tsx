import { ArrowUp, Square } from 'lucide-react'
import { useRef, useState, type KeyboardEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'

const MAX_LENGTH = 2000 // the backend rejects longer questions

export function Composer({ busy, onSend, onStop }: { busy: boolean; onSend: (text: string) => void; onStop: () => void }) {
  const { t } = useTranslation()
  const [value, setValue] = useState('')
  const ref = useRef<HTMLTextAreaElement>(null)

  const resize = () => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 192)}px`
  }

  const submit = () => {
    if (!value.trim() || busy) return
    onSend(value)
    setValue('')
    requestAnimationFrame(resize)
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends, Shift+Enter is a new line; Enter while composing (IME) must not send.
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="flex items-end gap-2 rounded-2xl border bg-card p-2 shadow-md transition-shadow focus-within:ring-2 focus-within:ring-ring">
      <textarea
        ref={ref}
        rows={1}
        value={value}
        maxLength={MAX_LENGTH}
        placeholder={t('chat.placeholder')}
        aria-label={t('chat.placeholder')}
        onChange={(e) => {
          setValue(e.target.value)
          resize()
        }}
        onKeyDown={onKeyDown}
        className="max-h-48 min-h-9 flex-1 resize-none bg-transparent px-2 py-1.5 text-[15px] leading-relaxed outline-none placeholder:text-muted-foreground"
      />
      {busy ? (
        <Button size="icon" variant="outline" onClick={onStop} aria-label={t('chat.stop')}>
          <Square className="size-4 fill-current" />
        </Button>
      ) : (
        <Button size="icon" onClick={submit} disabled={!value.trim()} aria-label={t('chat.send')}>
          <ArrowUp className="size-4" />
        </Button>
      )}
    </div>
  )
}
