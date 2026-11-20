import { getOrCreateId } from '@/lib/storage'
import { apiFetch, apiJson } from './client'
import type { DocumentInfo } from './types'

const owner = () => getOrCreateId('ownerId')

export const fetchDocuments = () => apiJson<DocumentInfo[]>(`/documents?owner_id=${owner()}`)

/** multipart/form-data: the browser sets the Content-Type (with the boundary) itself, so we must not. */
export function uploadDocument(file: File): Promise<DocumentInfo> {
  const form = new FormData()
  form.append('file', file)
  form.append('owner_id', owner())
  return apiJson<DocumentInfo>('/documents', { method: 'POST', body: form })
}

export async function deleteDocument(id: number): Promise<void> {
  await apiFetch(`/documents/${id}?owner_id=${owner()}`, { method: 'DELETE' })
}
