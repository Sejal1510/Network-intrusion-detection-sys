import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis } from "recharts"
import type { Severity } from "@/api/types"
import { severityMeta } from "@/lib/severity"

const SEVERITIES: Severity[] = ["low", "medium", "high", "critical"]

export function SeverityDistributionChart({ counts }: { counts: Record<Severity, number> }) {
  const data = SEVERITIES.map((severity) => ({
    severity,
    label: severityMeta(severity).label,
    count: counts[severity] ?? 0,
  }))

  return (
    <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-card)] p-4">
      <h3 className="mb-2 text-sm font-medium text-[var(--text-primary)]">Severity distribution</h3>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={data} margin={{ top: 16, right: 8, left: 8, bottom: 0 }}>
          <XAxis
            dataKey="label"
            tickLine={false}
            axisLine={{ stroke: "var(--axis)" }}
            tick={{ fill: "var(--text-muted)", fontSize: 12 }}
          />
          <Tooltip
            cursor={{ fill: "var(--gridline)" }}
            contentStyle={{
              background: "var(--surface-card)",
              border: "1px solid var(--border-hairline)",
              borderRadius: 6,
              fontSize: 12,
            }}
          />
          <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={48}>
            <LabelList dataKey="count" position="top" style={{ fill: "var(--text-secondary)", fontSize: 12 }} />
            {data.map((entry) => (
              <Cell key={entry.severity} fill={`var(${severityMeta(entry.severity).colorVar})`} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
