import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { deleteDocument, fetchDocuments, uploadDocument } from '@/api/documents'
import type { DocumentInfo } from '@/api/types'
import i18n from '@/i18n'
import { toastError } from '@/lib/errors'

const KEY = ['documents'] as const

export const useDocuments = () => useQuery({ queryKey: KEY, queryFn: fetchDocuments })

export function useUploadDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: uploadDocument,
    onSuccess: (doc) => {
      toast.success(i18n.t('documents.uploaded', { name: doc.filename }))
    },
    onError: toastError,
    // Refetch either way: after a failure the server may still have changed (e.g. a timeout after saving).
    onSettled: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

/** Optimistic: the card disappears at once; if the server refuses, it comes back and a toast says why. */
export function useDeleteDocument() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: deleteDocument,
    onMutate: async (id: number) => {
      await qc.cancelQueries({ queryKey: KEY }) // an in-flight refetch would overwrite the optimistic state
      const previous = qc.getQueryData<DocumentInfo[]>(KEY)
      qc.setQueryData<DocumentInfo[]>(KEY, (docs) => docs?.filter((d) => d.id !== id))
      return { previous }
    },
    onError: (e, _id, ctx) => {
      if (ctx?.previous) qc.setQueryData(KEY, ctx.previous) // roll back
      toastError(e)
    },
    onSuccess: () => toast.success(i18n.t('documents.deleted')),
    onSettled: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}
