import { SeverityBadge } from "@/components/common/SeverityBadge"
import { MitreChip } from "@/components/common/MitreChip"
import { EmptyState } from "@/components/common/EmptyState"
import { formatScore, formatTimestamp, titleCase } from "@/lib/format"
import type { LiveFeedEntry } from "@/hooks/useLiveFeed"

export function LiveFeedTable({ entries }: { entries: LiveFeedEntry[] }) {
  if (entries.length === 0) {
    return <EmptyState message="Waiting for traffic… start the capture agent to see predictions here." />
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
          </tr>
        </thead>
        <tbody>
          {entries.slice(0, 100).map((entry) => (
            <tr key={entry.id} className="border-b border-[var(--border-hairline)] last:border-0">
              <td
                className="whitespace-nowrap px-3 py-2 text-[var(--text-muted)]"
                style={{ fontVariantNumeric: "tabular-nums" }}
              >
                {formatTimestamp(entry.created_at)}
              </td>
              <td className="px-3 py-2 text-[var(--text-primary)]">
                {titleCase(String(entry.prediction))}
              </td>
              <td className="px-3 py-2">
                <SeverityBadge severity={entry.severity} />
              </td>
              <td className="px-3 py-2 tabular-nums text-[var(--text-secondary)]">
                {formatScore(entry.risk_score)}
              </td>
              <td className="px-3 py-2">{entry.mitre && <MitreChip mitre={entry.mitre} />}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
