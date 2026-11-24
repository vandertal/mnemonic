import type { ChatEvent } from '@/api/types'
import type { ChatMessage } from './use-chat'

/** i18n key for each class of LLM failure the server reports; anything else gets the generic one. */
const LLM_ERROR_KEYS: Record<string, string> = {
  quota: 'errors.llmQuota',
  overloaded: 'errors.llmOverloaded',
  blocked: 'errors.llmBlocked',
  timeout: 'errors.llmTimeout',
  busy: 'errors.busy',
}

export const llmErrorKey = (kind?: string): string => (kind && LLM_ERROR_KEYS[kind]) || 'errors.llm'

/**
 * One server event applied to the assistant message being streamed. Pure, so the retry protocol
 * is unit-tested without React:
 *  - `reset`: the server found the stream failed and starts the answer again, so the text received
 *    so far (and the tool notes of that attempt) must be thrown away, or it would be shown twice.
 *  - `error`: our localized sentence for the failure class; the server's English text is not shown.
 */
export function applyChatEvent(m: ChatMessage, ev: ChatEvent, t: (key: string) => string): ChatMessage {
  switch (ev.type) {
    case 'token':
      return { ...m, content: m.content + ev.text }
    case 'reset':
      return { ...m, content: '', tools: [], sources: [] }
    case 'sources':
      return { ...m, sources: ev.sources }
    case 'tool':
      return { ...m, tools: [...m.tools, ev.tool] }
    case 'refusal':
      return { ...m, refusalReason: ev.reason }
    case 'done':
      return { ...m, status: 'done', messageId: ev.messageId ?? undefined }
    case 'error':
      return { ...m, status: 'error', error: t(llmErrorKey(ev.kind)) }
  }
}
