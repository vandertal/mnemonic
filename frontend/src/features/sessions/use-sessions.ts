import { useInfiniteQuery, useMutation, useQueryClient, type InfiniteData } from '@tanstack/react-query'
import { createSession, deleteSession, fetchSessions, renameSession } from '@/api/sessions'
import type { ChatSession, SessionPage } from '@/api/types'
import { toastError } from '@/lib/errors'

export const SESSIONS_KEY = ['sessions'] as const

/** The title the server gives a chat until the first question renames it (store.DEFAULT_TITLE). */
export const DEFAULT_TITLE = 'New chat'

type Pages = InfiniteData<SessionPage, number>

/** First page of GET /sessions, more with fetchNextPage (offset pagination: `next` is the next offset). */
export function useSessions() {
  const query = useInfiniteQuery({
    queryKey: SESSIONS_KEY,
    queryFn: ({ pageParam }) => fetchSessions(pageParam),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next ?? undefined,
  })
  const sessions: ChatSession[] = query.data?.pages.flatMap((p) => p.items) ?? []
  return { ...query, sessions }
}

/** Drop one session from every loaded page (used by optimistic delete and by "404: it is gone"). */
function without(data: Pages | undefined, id: string): Pages | undefined {
  if (!data) return data
  return {
    ...data,
    pages: data.pages.map((p) =>
      p.items.some((s) => s.id === id) ? { ...p, items: p.items.filter((s) => s.id !== id), total: p.total - 1 } : p,
    ),
  }
}

export function useForgetSession() {
  const qc = useQueryClient()
  return (id: string) => qc.setQueryData<Pages>(SESSIONS_KEY, (d) => without(d, id))
}

export function useCreateSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: createSession,
    onSuccess: () => qc.invalidateQueries({ queryKey: SESSIONS_KEY }),
    onError: toastError,
  })
}

/** Optimistic: the new title shows at once; if the server refuses, the old one comes back. */
export function useRenameSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) => renameSession(id, title),
    onMutate: async ({ id, title }) => {
      await qc.cancelQueries({ queryKey: SESSIONS_KEY })
      const previous = qc.getQueryData<Pages>(SESSIONS_KEY)
      qc.setQueryData<Pages>(SESSIONS_KEY, (d) =>
        d && {
          ...d,
          pages: d.pages.map((p) => ({ ...p, items: p.items.map((s) => (s.id === id ? { ...s, title } : s)) })),
        },
      )
      return { previous }
    },
    onError: (e, _vars, ctx) => {
      if (ctx?.previous) qc.setQueryData(SESSIONS_KEY, ctx.previous)
      toastError(e)
    },
    onSettled: () => qc.invalidateQueries({ queryKey: SESSIONS_KEY }),
  })
}

/** Optimistic with rollback, like documents. */
export function useDeleteSession() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: deleteSession,
    onMutate: async (id: string) => {
      await qc.cancelQueries({ queryKey: SESSIONS_KEY })
      const previous = qc.getQueryData<Pages>(SESSIONS_KEY)
      qc.setQueryData<Pages>(SESSIONS_KEY, (d) => without(d, id))
      return { previous }
    },
    onError: (e, _id, ctx) => {
      if (ctx?.previous) qc.setQueryData(SESSIONS_KEY, ctx.previous) // roll back
      toastError(e)
    },
    onSettled: () => qc.invalidateQueries({ queryKey: SESSIONS_KEY }),
  })
}
