import { useEffect, useRef, useState } from "react"
import { SeverityBadge } from "@/components/common/SeverityBadge"
import { MitreChip } from "@/components/common/MitreChip"
import { EmptyState } from "@/components/common/EmptyState"
import { formatScore, formatTimestamp, titleCase } from "@/lib/format"
import type { LiveFeedEntry } from "@/hooks/useLiveFeed"

export function LiveFeedTable({ entries }: { entries: LiveFeedEntry[] }) {
  const seenIdsRef = useRef<Set<string> | null>(null)
  const [newIds, setNewIds] = useState<Set<string>>(new Set())

  // Marks genuinely new arrivals (not the initial page load) so they can
  // animate in and, if critical, give their badge a one-shot decaying
  // pulse -- real live-feed events, not a simulated trigger.
  useEffect(() => {
    const currentIds = new Set(entries.map((e) => e.id))
    if (seenIdsRef.current === null) {
      seenIdsRef.current = currentIds
      return
    }
    const fresh = new Set<string>()
    for (const id of currentIds) {
      if (!seenIdsRef.current.has(id)) fresh.add(id)
    }
    seenIdsRef.current = currentIds
    if (fresh.size === 0) return
    setNewIds(fresh)
    const timeout = setTimeout(() => setNewIds(new Set()), 1200)
    return () => clearTimeout(timeout)
  }, [entries])

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
          {entries.slice(0, 100).map((entry) => {
            const isNew = newIds.has(entry.id)
            return (
              <tr
                key={entry.id}
                className={`data-row border-b border-[var(--border-hairline)] last:border-0 ${isNew ? "data-row--enter" : ""}`}
              >
                <td
                  className="whitespace-nowrap px-3 py-2 font-mono text-[var(--text-muted)]"
                  style={{ fontVariantNumeric: "tabular-nums" }}
                >
                  {formatTimestamp(entry.created_at)}
                </td>
                <td className="px-3 py-2 text-[var(--text-primary)]">{titleCase(String(entry.prediction))}</td>
                <td className="px-3 py-2">
                  <SeverityBadge severity={entry.severity} pulse={isNew && entry.severity === "critical"} />
                </td>
                <td className="px-3 py-2 font-mono tabular-nums text-[var(--text-secondary)]">
                  {formatScore(entry.risk_score)}
                </td>
                <td className="px-3 py-2">{entry.mitre && <MitreChip mitre={entry.mitre} />}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
