export function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-dashed border-[var(--border-hairline)] p-8 text-center text-sm text-[var(--text-muted)]">
      {message}
    </div>
  )
}
