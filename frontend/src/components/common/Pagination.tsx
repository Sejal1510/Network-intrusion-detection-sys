export function Pagination({
  offset,
  limit,
  total,
  onOffsetChange,
}: {
  offset: number
  limit: number
  total: number
  onOffsetChange: (offset: number) => void
}) {
  const page = Math.floor(offset / limit) + 1
  const pageCount = Math.max(1, Math.ceil(total / limit))
  const canPrev = offset > 0
  const canNext = offset + limit < total

  return (
    <div className="flex items-center justify-between text-sm text-[var(--text-secondary)]">
      <span>
        {total === 0 ? "0 results" : `${offset + 1}-${Math.min(offset + limit, total)} of ${total}`}
      </span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={!canPrev}
          onClick={() => onOffsetChange(Math.max(0, offset - limit))}
          className="rounded border border-[var(--border-hairline)] px-2 py-1 disabled:opacity-40"
        >
          Previous
        </button>
        <span>
          Page {page} of {pageCount}
        </span>
        <button
          type="button"
          disabled={!canNext}
          onClick={() => onOffsetChange(offset + limit)}
          className="rounded border border-[var(--border-hairline)] px-2 py-1 disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </div>
  )
}
