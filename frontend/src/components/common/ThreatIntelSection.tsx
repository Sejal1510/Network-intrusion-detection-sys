import { useAlertEnrichment } from "@/hooks/useAlertEnrichment"
import type { EnrichmentResult, TiVerdict } from "@/api/types"

const VERDICT_META: Record<TiVerdict, { label: string; colorVar: string }> = {
  malicious: { label: "Malicious", colorVar: "--status-critical" },
  suspicious: { label: "Suspicious", colorVar: "--status-warning" },
  benign: { label: "Benign", colorVar: "--status-good" },
  unknown: { label: "Unknown", colorVar: "--text-muted" },
}

function VerdictPill({ result }: { result: EnrichmentResult }) {
  const meta = VERDICT_META[result.verdict]
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium"
      style={{
        color: `var(${meta.colorVar})`,
        borderColor: `var(${meta.colorVar})`,
        backgroundColor: `color-mix(in srgb, var(${meta.colorVar}) 12%, transparent)`,
      }}
      title={`${result.provider}: ${meta.label} (confidence ${result.confidence.toFixed(0)})`}
    >
      {result.provider}: {meta.label}
    </span>
  )
}

/**
 * Read-only threat-intel context for one alert's indicators
 * (`GET /history/alerts/{id}/enrichment`) -- purely additive display,
 * never influences the severity/verdict already decided by the ML
 * classifier or signature match above it. Handles three states
 * explicitly: no routable indicators at all (always true for
 * API-sourced/`/predict` alerts -- NSL-KDD has no IP field), dispatched
 * but not yet resolved (enrichment runs asynchronously, see
 * docs/THREAT_INTEL.md), and resolved results grouped by indicator.
 */
export function ThreatIntelSection({ alertId, expanded }: { alertId: string; expanded: boolean }) {
  const { data, isLoading } = useAlertEnrichment(alertId, expanded)
  const items = data?.items ?? []

  if (items.length === 0 && (isLoading || !data)) {
    return (
      <p className="text-xs text-[var(--text-muted)]" role="status">
        Checking threat intelligence…
      </p>
    )
  }

  if (items.length === 0) {
    return (
      <p className="text-xs text-[var(--text-muted)]">
        No network indicators available for this detection.
      </p>
    )
  }

  const byIndicator = new Map<string, EnrichmentResult[]>()
  for (const item of items) {
    const key = `${item.indicator_role}:${item.indicator}`
    const group = byIndicator.get(key) ?? []
    group.push(item)
    byIndicator.set(key, group)
  }

  return (
    <div className="space-y-2">
      {[...byIndicator.entries()].map(([key, results]) => (
        <div key={key} className="flex flex-wrap items-center gap-1.5">
          <span className="font-mono text-xs text-[var(--text-secondary)]">
            {results[0].indicator}
          </span>
          <span className="text-xs text-[var(--text-muted)]">
            ({results[0].indicator_role === "src" ? "source" : "destination"})
          </span>
          {results.map((result) => (
            <VerdictPill key={result.provider} result={result} />
          ))}
        </div>
      ))}
    </div>
  )
}
