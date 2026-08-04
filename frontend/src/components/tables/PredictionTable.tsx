import { EmptyState } from "@/components/common/EmptyState"
import { PredictionRow } from "@/components/tables/PredictionRow"
import type { PredictionHistoryItem } from "@/api/types"

export function PredictionTable({ items }: { items: PredictionHistoryItem[] }) {
  if (items.length === 0) {
    return <EmptyState message="No predictions match the current filters." />
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--border-hairline)]">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-[var(--border-hairline)] text-xs uppercase tracking-wide text-[var(--text-muted)]">
            <th className="px-3 py-2 font-medium">Time</th>
            <th className="px-3 py-2 font-medium">Prediction</th>
            <th className="px-3 py-2 font-medium">Severity</th>
            <th className="px-3 py-2 font-medium">Risk</th>
            <th className="px-3 py-2 font-medium">MITRE</th>
            <th className="px-3 py-2 font-medium">Source</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <PredictionRow key={item.id} item={item} />
          ))}
        </tbody>
      </table>
    </div>
  )
}
