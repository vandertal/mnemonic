export interface Source {
  id: number
  file_path: string
  heading: string
  similarity: number
}

export interface ToolEvent {
  name: string
  args: Record<string, unknown>
  result: string
}

export interface StoredMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  sources: Source[] | null
  created_at: string
}

export interface Chunk {
  id: number
  file: string
  heading: string
  content: string
}

/** What the server streams for one answer, already parsed. */
export type ChatEvent =
  | { type: 'token'; text: string }
  | { type: 'sources'; sources: Source[] }
  | { type: 'tool'; tool: ToolEvent }
  | { type: 'done'; messageId: number | null }
  | { type: 'error'; message: string }
