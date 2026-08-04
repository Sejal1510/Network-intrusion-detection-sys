import { EmptyState } from "@/components/common/EmptyState"
import { AlertRow } from "@/components/tables/AlertRow"
import type { AlertHistoryItem } from "@/api/types"

export function AlertTable({ alerts }: { alerts: AlertHistoryItem[] }) {
  if (alerts.length === 0) {
    return <EmptyState message="No alerts match the current filters." />
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--border-hairline)]">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-[var(--border-hairline)] text-xs uppercase tracking-wide text-[var(--text-muted)]">
            <th className="px-3 py-2 font-medium">Time</th>
            <th className="px-3 py-2 font-medium">Severity</th>
            <th className="px-3 py-2 font-medium">Alert</th>
            <th className="px-3 py-2 font-medium">Risk</th>
            <th className="px-3 py-2 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((alert) => (
            <AlertRow key={alert.id} alert={alert} />
          ))}
        </tbody>
      </table>
    </div>
  )
}
