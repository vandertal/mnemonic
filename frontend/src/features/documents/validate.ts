// Mirrors the backend (documents.ALLOWED_EXTENSIONS, max_documents_per_owner). The server still
// re-checks everything: this only saves a round trip and gives field-level messages.
export const ALLOWED_EXTENSIONS = ['.md', '.txt', '.pdf'] as const
export const MAX_DOCUMENTS = 5

const parsed = Number(import.meta.env.VITE_MAX_UPLOAD_MB)
export const MAX_UPLOAD_MB = Number.isFinite(parsed) && parsed > 0 ? parsed : 1

export interface FileProblem {
  key: string // i18n key under documents.*
  params?: Record<string, string | number>
}

export function validateFile(file: File, currentCount: number): FileProblem | null {
  const name = file.name.toLowerCase()
  if (!ALLOWED_EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return { key: 'documents.errType', params: { types: ALLOWED_EXTENSIONS.join(', ') } }
  }
  if (file.size === 0) return { key: 'documents.errEmpty' }
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) return { key: 'documents.errSize', params: { mb: MAX_UPLOAD_MB } }
  if (currentCount >= MAX_DOCUMENTS) return { key: 'documents.errLimit', params: { max: MAX_DOCUMENTS } }
  return null
}
