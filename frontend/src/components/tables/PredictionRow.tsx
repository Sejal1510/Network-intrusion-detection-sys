import { SeverityBadge } from "@/components/common/SeverityBadge"
import { MitreChip } from "@/components/common/MitreChip"
import { formatTimestamp, titleCase } from "@/lib/format"
import type { PredictionHistoryItem } from "@/api/types"

export function PredictionRow({ item }: { item: PredictionHistoryItem }) {
  return (
    <tr className="data-row border-b border-[var(--border-hairline)] align-top last:border-0">
      <td
        className="whitespace-nowrap px-3 py-2 text-[var(--text-muted)]"
        style={{ fontVariantNumeric: "tabular-nums" }}
      >
        {formatTimestamp(item.created_at)}
      </td>
      <td className="px-3 py-2 text-[var(--text-primary)]">{titleCase(item.prediction)}</td>
      <td className="px-3 py-2">
        <SeverityBadge severity={item.severity} />
      </td>
      <td className="px-3 py-2 tabular-nums text-[var(--text-secondary)]">
        {item.risk_score.toFixed(1)}
      </td>
      <td className="px-3 py-2">{item.mitre && <MitreChip mitre={item.mitre} />}</td>
      <td className="px-3 py-2 text-xs text-[var(--text-muted)]">{item.source}</td>
    </tr>
  )
}
