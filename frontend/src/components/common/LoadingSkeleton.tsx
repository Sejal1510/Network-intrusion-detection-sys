export function LoadingSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2" role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div
          key={i}
          className="h-8 animate-pulse rounded bg-[var(--gridline)]"
          style={{ width: `${100 - i * 8}%` }}
        />
      ))}
    </div>
  )
}
