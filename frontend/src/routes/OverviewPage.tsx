import { useMemo } from "react"
import { StatTile } from "@/components/common/StatTile"
import { SeverityBadge } from "@/components/common/SeverityBadge"
import { ErrorState } from "@/components/common/ErrorState"
import { DegradedModeBanner } from "@/components/layout/DegradedModeBanner"
import { ConnectionStatusIndicator } from "@/components/layout/ConnectionStatusIndicator"
import { CoreHubVisual } from "@/components/layout/CoreHubVisual"
import { LiveFeedTable } from "@/components/tables/LiveFeedTable"
import { SeverityDistributionChart } from "@/components/charts/SeverityDistributionChart"
import { PredictionsOverTimeChart } from "@/components/charts/PredictionsOverTimeChart"
import { useLiveFeed, type LiveFeedEntry } from "@/hooks/useLiveFeed"
import { useRules } from "@/hooks/useRules"
import { formatPercent } from "@/lib/format"
import type { Severity } from "@/api/types"

/** Shaped like a few rows of the real rules list instead of a generic bar list. */
function RulesListSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading"
      className="divide-y divide-[var(--gridline)] rounded-lg border border-[var(--border-hairline)]"
    >
      {Array.from({ length: 3 }, (_, i) => (
        <div key={i} className="flex items-start justify-between gap-4 px-3 py-2.5">
          <div className="space-y-1.5">
            <div className="h-3 w-40 animate-pulse rounded bg-[var(--gridline)]" />
            <div className="h-3 w-56 animate-pulse rounded bg-[var(--gridline)]" />
          </div>
          <div className="h-4 w-14 animate-pulse rounded bg-[var(--gridline)]" />
        </div>
      ))}
    </div>
  )
}

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
    <div className="space-y-8">
      <div className="relative min-h-[170px] space-y-3 py-2">
        <CoreHubVisual />
        <div className="flex items-center justify-between gap-4">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Network overview</h2>
          <ConnectionStatusIndicator status={status} />
        </div>
        <p className="max-w-xl text-sm text-[var(--text-muted)]">
          Live posture across every monitored segment — one detection core evaluating every flow
          against the trained classifier and the signature rule set together.
        </p>
      </div>

      <DegradedModeBanner />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatTile label="Total predictions" value={stats.total} />
        <StatTile label="Normal" value={stats.normalCount} accent="good" />
        <StatTile label="Attacks detected" value={stats.attackCount} accent="critical" />
        <StatTile
          label="Safety score"
          value={stats.total === 0 ? "—" : formatPercent(stats.normalCount / stats.total)}
          accent="good"
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
        <div className="mb-2 flex items-baseline justify-between gap-2">
          <h3 className="text-sm font-medium text-[var(--text-primary)]">Detection rules armed</h3>
          {rules && <span className="text-xs text-[var(--text-muted)]">{rules.length} signature rules</span>}
        </div>
        {rulesLoading && <RulesListSkeleton />}
        {rulesError && <ErrorState message="Could not load detection rules." />}
        {rules && (
          <div className="divide-y divide-[var(--gridline)] rounded-lg border border-[var(--border-hairline)]">
            {rules.map((rule) => (
              <div
                key={rule.id}
                className="flex items-start justify-between gap-4 px-3 py-2.5 transition-colors hover:bg-[color-mix(in_srgb,var(--text-primary)_3%,transparent)]"
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
