import { apiFetch, apiJson } from './client'
import type { DocumentInfo } from './types'

export const fetchDocuments = () => apiJson<DocumentInfo[]>('/documents')

/** multipart/form-data: the browser sets the Content-Type (with the boundary) itself, so we must not. */
export function uploadDocument(file: File): Promise<DocumentInfo> {
  const form = new FormData()
  form.append('file', file)
  return apiJson<DocumentInfo>('/documents', { method: 'POST', body: form })
}

export async function deleteDocument(id: number): Promise<void> {
  await apiFetch(`/documents/${id}`, { method: 'DELETE' })
}
