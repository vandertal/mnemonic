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

export interface DocumentInfo {
  id: number
  filename: string
  chunks: number
  created_at: string
}

export interface Flashcard {
  question: string
  answer: string
  source_chunk_id: number | null
}

export interface FlashcardSet {
  cards: Flashcard[]
}

export interface User {
  id: string
  email: string
  created_at: string
}

export interface ChatSession {
  id: string
  title: string
  created_at: string
  updated_at: string
}

/** Offset pagination: `next` is the offset of the following page, null on the last one. */
export interface SessionPage {
  items: ChatSession[]
  total: number
  limit: number
  offset: number
  next: number | null
}

export type Ranker = 'bm25' | 'tfidf'
export type SearchMode = 'all' | 'any'

export interface Snippet {
  text: string
  /** [start, end) offsets into `text`, counted in Unicode code points (Python), not UTF-16 units. */
  highlights: [number, number][]
}

export interface SearchHit {
  chunk_id: number
  document: string
  heading: string
  score: number
  snippet: Snippet
  matched_terms: string[]
}

export interface TermExplanation {
  term: string
  tf: number
  df: number
  idf: number
  contribution: number
}

export interface Explanation {
  chunk_id: number
  document: string
  ranker: Ranker
  n_docs: number
  avgdl: number
  doc_length: number
  terms: TermExplanation[]
  score: number
}
