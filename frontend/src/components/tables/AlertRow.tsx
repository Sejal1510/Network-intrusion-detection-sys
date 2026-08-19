import { useState } from "react"
import { SeverityBadge } from "@/components/common/SeverityBadge"
import { MitreChip } from "@/components/common/MitreChip"
import { AlertSourceBadge } from "@/components/common/AlertSourceBadge"
import { ThreatIntelSection } from "@/components/common/ThreatIntelSection"
import { formatTimestamp } from "@/lib/format"
import { useAcknowledgeAlert } from "@/hooks/useAcknowledgeAlert"
import type { AlertHistoryItem } from "@/api/types"

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      viewBox="0 0 16 16"
      width="12"
      height="12"
      aria-hidden="true"
      fill="none"
      className="mt-1 shrink-0 transition-transform"
      style={{ transform: expanded ? "rotate(90deg)" : "rotate(0deg)" }}
    >
      <path
        d="M6 3.5l5 4.5-5 4.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function AlertRow({ alert }: { alert: AlertHistoryItem }) {
  const [expanded, setExpanded] = useState(false)
  const acknowledge = useAcknowledgeAlert()

  return (
    <>
      <tr className="data-row border-b border-[var(--border-hairline)] align-top last:border-0">
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
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            aria-expanded={expanded}
            aria-controls={`alert-detail-${alert.id}`}
            className="flex w-full items-start gap-1.5 text-left"
          >
            <ChevronIcon expanded={expanded} />
            <div>
              <div className="font-medium text-[var(--text-primary)]">{alert.title}</div>
              <div className="text-xs text-[var(--text-secondary)]">{alert.message}</div>
              {alert.mitre && (
                <div className="mt-1">
                  <MitreChip mitre={alert.mitre} />
                </div>
              )}
            </div>
          </button>
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
      {expanded && (
        <tr className="border-b border-[var(--border-hairline)] last:border-0">
          <td
            id={`alert-detail-${alert.id}`}
            colSpan={5}
            className="bg-[var(--surface-elevated)] px-4 py-3"
          >
            <div className="grid gap-4 sm:grid-cols-3">
              <section>
                <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                  Detection
                </h4>
                <div className="flex flex-wrap items-center gap-1.5">
                  <AlertSourceBadge source={alert.source} />
                  <SeverityBadge severity={alert.level} />
                </div>
              </section>
              <section>
                <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                  MITRE ATT&amp;CK
                </h4>
                {alert.mitre ? (
                  <MitreChip mitre={alert.mitre} />
                ) : (
                  <p className="text-xs text-[var(--text-muted)]">No technique mapping.</p>
                )}
              </section>
              <section>
                <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
                  Threat Intelligence
                </h4>
                <ThreatIntelSection alertId={alert.id} expanded={expanded} />
              </section>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}
