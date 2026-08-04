export function StatTile({
  label,
  value,
  delta,
}: {
  label: string
  value: string | number
  delta?: string
}) {
  return (
    <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-card)] p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]">
        {label}
      </div>
      <div className="mt-1 text-2xl font-semibold text-[var(--text-primary)]" style={{ fontVariantNumeric: "proportional-nums" }}>
        {value}
      </div>
      {delta && <div className="mt-0.5 text-xs text-[var(--text-secondary)]">{delta}</div>}
    </div>
  )
}
