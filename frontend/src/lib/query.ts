import { QueryClient } from '@tanstack/react-query'
import { ApiError } from '@/api/errors'

/** Retry only what can heal by itself: network errors and 5xx. A 4xx (bad input, 401, 404) will not. */
export const retryPolicy = (failureCount: number, error: unknown) =>
  !(error instanceof ApiError && error.status >= 400 && error.status < 500) && failureCount < 2

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: retryPolicy, staleTime: 30_000, refetchOnWindowFocus: false },
    mutations: { retry: false }, // never repeat a POST/DELETE on its own
  },
})
