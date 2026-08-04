import { SeverityBadge } from "@/components/common/SeverityBadge"
import { MitreChip } from "@/components/common/MitreChip"
import { ExplanationBarChart } from "@/components/forms/ExplanationBarChart"
import { formatPercent, formatScore, titleCase } from "@/lib/format"
import type { PredictResponse } from "@/api/types"

export function PredictionResultCard({ result }: { result: PredictResponse }) {
  return (
    <div className="space-y-4 rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-card)] p-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-wide text-[var(--text-muted)]">Prediction</div>
          <div className="text-xl font-semibold text-[var(--text-primary)]">
            {titleCase(String(result.prediction))}
          </div>
        </div>
        <SeverityBadge severity={result.severity} />
      </div>

      {result.alert_id && (
        <div
          className="rounded border p-2 text-xs"
          style={{ borderColor: "var(--status-critical)", color: "var(--status-critical)" }}
        >
          This prediction raised an alert (id: {result.alert_id}).
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
        <div>
          <div className="text-xs text-[var(--text-muted)]">Risk score</div>
          <div className="font-medium text-[var(--text-primary)]">
            {formatScore(result.risk_score.score)} / 100
          </div>
        </div>
        {result.confidence !== null && (
          <div>
            <div className="text-xs text-[var(--text-muted)]">Confidence</div>
            <div className="font-medium text-[var(--text-primary)]">
              {formatPercent(result.confidence)}
            </div>
          </div>
        )}
        {result.anomaly_score !== null && (
          <div>
            <div className="text-xs text-[var(--text-muted)]">Anomaly score</div>
            <div className="font-medium text-[var(--text-primary)]">
              {formatPercent(result.anomaly_score)}
            </div>
          </div>
        )}
      </div>

      {result.probabilities && (
        <div>
          <div className="mb-1 text-xs text-[var(--text-muted)]">Class probabilities</div>
          <div className="flex flex-wrap gap-2 text-xs">
            {Object.entries(result.probabilities)
              .sort(([, a], [, b]) => b - a)
              .map(([label, prob]) => (
                <span
                  key={label}
                  className="rounded border border-[var(--border-hairline)] px-2 py-1"
                >
                  {titleCase(label)}: {formatPercent(prob)}
                </span>
              ))}
          </div>
        </div>
      )}

      {result.mitre && (
        <div>
          <div className="mb-1 text-xs text-[var(--text-muted)]">MITRE ATT&CK</div>
          <MitreChip mitre={result.mitre} />
        </div>
      )}

      {result.explanation && <ExplanationBarChart explanation={result.explanation} />}
    </div>
  )
}
