import { useMemo } from "react"
import { StatTile } from "@/components/common/StatTile"
import { DegradedModeBanner } from "@/components/layout/DegradedModeBanner"
import { ConnectionStatusIndicator } from "@/components/layout/ConnectionStatusIndicator"
import { LiveFeedTable } from "@/components/tables/LiveFeedTable"
import { SeverityDistributionChart } from "@/components/charts/SeverityDistributionChart"
import { PredictionsOverTimeChart } from "@/components/charts/PredictionsOverTimeChart"
import { useLiveFeed, type LiveFeedEntry } from "@/hooks/useLiveFeed"
import { formatPercent } from "@/lib/format"
import type { Severity } from "@/api/types"

function isAttack(entry: LiveFeedEntry): boolean {
  if (entry.attack_category) return entry.attack_category !== "normal"
  if (typeof entry.prediction === "number") return entry.prediction === 1
  return String(entry.prediction).toLowerCase() !== "normal"
}

export function OverviewPage() {
  const { status, entries } = useLiveFeed()

  const stats = useMemo(() => {
    const total = entries.length
    const attackCount = entries.filter(isAttack).length
    const normalCount = total - attackCount
    const severityCounts = entries.reduce(
      (acc, e) => {
        acc[e.severity] += 1
        return acc
      },
      { low: 0, medium: 0, high: 0, critical: 0 } as Record<Severity, number>
    )
    return { total, attackCount, normalCount, severityCounts }
  }, [entries])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">Overview</h2>
        <ConnectionStatusIndicator status={status} />
      </div>

      <DegradedModeBanner />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatTile label="Total predictions" value={stats.total} />
        <StatTile label="Normal" value={stats.normalCount} />
        <StatTile label="Attacks detected" value={stats.attackCount} />
        <StatTile
          label="Safety score"
          value={stats.total === 0 ? "—" : formatPercent(stats.normalCount / stats.total)}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <SeverityDistributionChart counts={stats.severityCounts} />
        <PredictionsOverTimeChart entries={entries} />
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium text-[var(--text-primary)]">Live feed</h3>
        <LiveFeedTable entries={entries} />
      </div>
    </div>
  )
}
