import { SeverityBadge } from "@/components/common/SeverityBadge"
import { MitreChip } from "@/components/common/MitreChip"
import { formatTimestamp } from "@/lib/format"
import { useAcknowledgeAlert } from "@/hooks/useAcknowledgeAlert"
import type { AlertHistoryItem } from "@/api/types"

export function AlertRow({ alert }: { alert: AlertHistoryItem }) {
  const acknowledge = useAcknowledgeAlert()

  return (
    <tr className="border-b border-[var(--border-hairline)] align-top last:border-0">
      <td
        className="whitespace-nowrap px-3 py-2 text-[var(--text-muted)]"
        style={{ fontVariantNumeric: "tabular-nums" }}
      >
        {formatTimestamp(alert.created_at)}
      </td>
      <td className="px-3 py-2">
        <SeverityBadge severity={alert.level} />
      </td>
      <td className="px-3 py-2">
        <div className="font-medium text-[var(--text-primary)]">{alert.title}</div>
        <div className="text-xs text-[var(--text-secondary)]">{alert.message}</div>
        {alert.mitre && (
          <div className="mt-1">
            <MitreChip mitre={alert.mitre} />
          </div>
        )}
      </td>
      <td className="px-3 py-2 tabular-nums text-[var(--text-secondary)]">
        {alert.risk_score.toFixed(1)}
      </td>
      <td className="px-3 py-2">
        {alert.acknowledged ? (
          <span className="text-xs text-[var(--text-muted)]">Acknowledged</span>
        ) : (
          <button
            type="button"
            onClick={() => acknowledge.mutate(alert.id)}
            disabled={acknowledge.isPending}
            className="rounded border border-[var(--border-hairline)] px-2 py-1 text-xs hover:bg-[var(--gridline)] disabled:opacity-50"
          >
            {acknowledge.isPending ? "Acknowledging…" : "Acknowledge"}
          </button>
        )}
      </td>
    </tr>
  )
}
