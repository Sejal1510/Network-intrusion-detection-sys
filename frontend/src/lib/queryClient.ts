import { QueryClient } from "@tanstack/react-query"
import { ApiError } from "@/api/client"

const MAX_RETRIES = 2

/**
 * TanStack Query's own default (retry every failure 3x with exponential
 * backoff) doesn't distinguish a transient network blip from a 4xx that
 * will never succeed on retry -- most visibly, a session-expiry 401
 * (see useUserAuth's clearLocalSession) used to sit retrying for several
 * seconds before the real redirect-to-login ever happened. Only network/
 * 5xx failures are worth retrying; any ApiError below 500 is retried zero
 * times.
 */
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && error.status < 500) return false
  return failureCount < MAX_RETRIES
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: shouldRetryQuery,
      },
    },
  })
}
