/**
 * Distinguishes which detection mechanism raised an alert -- ML
 * (`nids.api.alerts.generate_alert`) or a signature match
 * (`nids.api.rules.generate_rule_alert`, always `source: "rule"`).
 * `AlertHistoryItem.source` is otherwise overloaded (an ML-sourced
 * alert's `source` is actually its *input path*, "api"/"agent", not a
 * detection-mechanism label) -- "rule" is the one value that
 * unambiguously means signature-based, so anything else here is ML.
 */
export function AlertSourceBadge({ source }: { source: string }) {
  const isRule = source === "rule"
  return (
    <span
      className="inline-flex items-center rounded border px-1.5 py-0.5 text-xs font-medium"
      style={{
        color: isRule ? "var(--status-warning)" : "var(--text-secondary)",
        borderColor: isRule ? "var(--status-warning)" : "var(--border-hairline)",
        backgroundColor: isRule
          ? "color-mix(in srgb, var(--status-warning) 12%, transparent)"
          : "transparent",
      }}
      title={isRule ? "Raised by a signature/rule match" : "Raised by the ML classifier"}
    >
      {isRule ? "Signature" : "ML"}
    </span>
  )
}
