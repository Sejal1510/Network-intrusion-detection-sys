import { useMemo } from "react"
import { StatTile } from "@/components/common/StatTile"
import { SeverityBadge } from "@/components/common/SeverityBadge"
import { SeverityDistributionChart } from "@/components/charts/SeverityDistributionChart"
import { formatPercent, formatScore, titleCase } from "@/lib/format"
import type { ZippedRow } from "@/lib/csv"
import type { BatchPredictSummary, Severity } from "@/api/types"

function isAttackRow(row: ZippedRow): boolean {
  const { result } = row
  if (result.attack_category) return result.attack_category !== "normal"
  if (typeof result.prediction === "number") return result.prediction === 1
  return String(result.prediction).toLowerCase() !== "normal"
}

export function BatchSummaryPanel({
  summary,
  zippedRows,
}: {
  summary: BatchPredictSummary
  zippedRows: ZippedRow[]
}) {
  const stats = useMemo(() => {
    const severityCounts = zippedRows.reduce(
      (acc, r) => {
        acc[r.result.severity] += 1
        return acc
      },
      { low: 0, medium: 0, high: 0, critical: 0 } as Record<Severity, number>
    )

    const byProtocol = new Map<string, { total: number; attacks: number }>()
    for (const row of zippedRows) {
      const key = row.row.protocol_type ?? "unknown"
      const bucket = byProtocol.get(key) ?? { total: 0, attacks: 0 }
      bucket.total += 1
      if (isAttackRow(row)) bucket.attacks += 1
      byProtocol.set(key, bucket)
    }

    const topDangerous = [...zippedRows]
      .sort((a, b) => b.result.risk_score.score - a.result.risk_score.score)
      .slice(0, 10)

    const attackCount = zippedRows.filter(isAttackRow).length

    return { severityCounts, byProtocol, topDangerous, attackCount }
  }, [zippedRows])

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatTile label="Total records" value={summary.total_records} />
        <StatTile label="Attacks detected" value={stats.attackCount} />
        <StatTile
          label="Healthy %"
          value={
            summary.total_records === 0
              ? "—"
              : formatPercent((summary.total_records - stats.attackCount) / summary.total_records)
          }
        />
        <StatTile
          label="High + critical"
          value={stats.severityCounts.high + stats.severityCounts.critical}
        />
      </div>

      <SeverityDistributionChart counts={stats.severityCounts} />

      <div>
        <h3 className="mb-2 text-sm font-medium text-[var(--text-primary)]">By protocol</h3>
        <div className="overflow-x-auto rounded-lg border border-[var(--border-hairline)]">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-[var(--border-hairline)] text-xs uppercase tracking-wide text-[var(--text-muted)]">
                <th className="px-3 py-2 font-medium">Protocol</th>
                <th className="px-3 py-2 font-medium">Total</th>
                <th className="px-3 py-2 font-medium">Attacks</th>
              </tr>
            </thead>
            <tbody>
              {[...stats.byProtocol.entries()].map(([protocol, counts]) => (
                <tr key={protocol} className="border-b border-[var(--border-hairline)] last:border-0">
                  <td className="px-3 py-2">{protocol}</td>
                  <td className="px-3 py-2 tabular-nums">{counts.total}</td>
                  <td className="px-3 py-2 tabular-nums">{counts.attacks}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium text-[var(--text-primary)]">
          Top 10 most dangerous connections
        </h3>
        <div className="overflow-x-auto rounded-lg border border-[var(--border-hairline)]">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-[var(--border-hairline)] text-xs uppercase tracking-wide text-[var(--text-muted)]">
                <th className="px-3 py-2 font-medium">Protocol</th>
                <th className="px-3 py-2 font-medium">Service</th>
                <th className="px-3 py-2 font-medium">Prediction</th>
                <th className="px-3 py-2 font-medium">Severity</th>
                <th className="px-3 py-2 font-medium">Risk</th>
              </tr>
            </thead>
            <tbody>
              {stats.topDangerous.map((zipped, i) => (
                <tr key={i} className="border-b border-[var(--border-hairline)] last:border-0">
                  <td className="px-3 py-2">{zipped.row.protocol_type}</td>
                  <td className="px-3 py-2">{zipped.row.service}</td>
                  <td className="px-3 py-2">{titleCase(String(zipped.result.prediction))}</td>
                  <td className="px-3 py-2">
                    <SeverityBadge severity={zipped.result.severity} />
                  </td>
                  <td className="px-3 py-2 tabular-nums">{formatScore(zipped.result.risk_score.score)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
