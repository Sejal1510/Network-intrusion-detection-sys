import { Card } from "@/components/common/Card"

export function StatTile({
  label,
  value,
  delta,
  accent,
}: {
  label: string
  value: string | number
  delta?: string
  accent?: "good" | "critical"
}) {
  return (
    <Card accent={accent}>
      <div className="text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]">{label}</div>
      <div
        className="mt-1 font-mono text-2xl font-semibold text-[var(--text-primary)]"
        style={{ fontVariantNumeric: "tabular-nums" }}
      >
        {value}
      </div>
      {delta && <div className="mt-0.5 text-xs text-[var(--text-secondary)]">{delta}</div>}
    </Card>
  )
}
