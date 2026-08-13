/**
 * Suspense fallback for a lazy-loaded route chunk. Can't be shaped to the
 * page's real content the way TableSkeleton/MetricsSkeleton are -- at this
 * point React doesn't know which page is loading yet -- so this is
 * necessarily generic. Only ever visible on a route's first visit in a
 * session, before its chunk is cached.
 */
export function RouteLoadingFallback() {
  return (
    <div role="status" aria-label="Loading page" className="flex min-h-[40vh] items-center justify-center">
      <div
        className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--border-hairline)]"
        style={{ borderTopColor: "var(--accent)" }}
      />
    </div>
  )
}
