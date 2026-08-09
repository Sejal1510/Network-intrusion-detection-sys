import { useMemo } from "react"
import { StatTile } from "@/components/common/StatTile"
import { SeverityBadge } from "@/components/common/SeverityBadge"
import { LoadingSkeleton } from "@/components/common/LoadingSkeleton"
import { ErrorState } from "@/components/common/ErrorState"
import { DegradedModeBanner } from "@/components/layout/DegradedModeBanner"
import { ConnectionStatusIndicator } from "@/components/layout/ConnectionStatusIndicator"
import { LiveFeedTable } from "@/components/tables/LiveFeedTable"
import { SeverityDistributionChart } from "@/components/charts/SeverityDistributionChart"
import { PredictionsOverTimeChart } from "@/components/charts/PredictionsOverTimeChart"
import { useLiveFeed, type LiveFeedEntry } from "@/hooks/useLiveFeed"
import { useRules } from "@/hooks/useRules"
import { formatPercent } from "@/lib/format"
import type { Severity } from "@/api/types"

function isAttack(entry: LiveFeedEntry): boolean {
  if (entry.attack_category) return entry.attack_category !== "normal"
  if (typeof entry.prediction === "number") return entry.prediction === 1
  return String(entry.prediction).toLowerCase() !== "normal"
}

export function OverviewPage() {
  const { status, entries } = useLiveFeed()
  const { data: rules, isLoading: rulesLoading, isError: rulesError } = useRules()

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

      <div>
        <h3 className="mb-2 text-sm font-medium text-[var(--text-primary)]">
          Detection rules armed
        </h3>
        {rulesLoading && <LoadingSkeleton rows={3} />}
        {rulesError && <ErrorState message="Could not load detection rules." />}
        {rules && (
          <div className="space-y-2">
            {rules.map((rule) => (
              <div
                key={rule.id}
                className="flex items-start justify-between gap-4 rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-card)] p-3"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs text-[var(--text-muted)]">{rule.id}</span>
                    <span className="text-sm font-medium text-[var(--text-primary)]">{rule.name}</span>
                  </div>
                  <p className="mt-0.5 text-xs text-[var(--text-secondary)]">{rule.description}</p>
                </div>
                <SeverityBadge severity={rule.severity} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
