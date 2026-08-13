/**
 * Loading placeholder shaped like the real table it precedes (bordered
 * wrapper, header bar, N rows) instead of a generic bar list, so nothing
 * shifts layout when data lands. `animate-pulse` is a plain CSS animation,
 * already covered by index.css's global `prefers-reduced-motion` override.
 */
export function TableSkeleton({ rows = 5, columns = 4 }: { rows?: number; columns?: number }) {
  const cols = Array.from({ length: columns })

  return (
    <div className="overflow-hidden rounded-lg border border-[var(--border-hairline)]" role="status" aria-label="Loading">
      <div className="flex gap-6 border-b border-[var(--border-hairline)] px-3 py-2.5">
        {cols.map((_, i) => (
          <div key={i} className="h-3 w-16 animate-pulse rounded bg-[var(--gridline)]" />
        ))}
      </div>
      <div className="divide-y divide-[var(--border-hairline)]">
        {Array.from({ length: rows }, (_, r) => (
          <div key={r} className="flex items-center gap-6 px-3 py-3">
            {cols.map((_, c) => (
              <div
                key={c}
                className="h-3.5 flex-1 animate-pulse rounded bg-[var(--gridline)]"
                style={{ maxWidth: c === 0 ? "20%" : c === columns - 1 ? "12%" : undefined }}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}
