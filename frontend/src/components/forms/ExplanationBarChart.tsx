import { Bar, BarChart, Cell, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { Card } from "@/components/common/Card"
import type { Explanation } from "@/api/types"

export function ExplanationBarChart({ explanation }: { explanation: Explanation }) {
  const data = [...explanation.top_features]
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
    .map((f) => ({
      name: `${f.feature} = ${f.value}`,
      contribution: f.contribution,
      direction: f.direction,
    }))

  return (
    <Card>
      <h3 className="mb-1 text-sm font-medium text-[var(--text-primary)]">Why this prediction</h3>
      <p className="mb-3 text-xs text-[var(--text-secondary)]">{explanation.summary}</p>
      <ResponsiveContainer width="100%" height={Math.max(160, data.length * 28)}>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, left: 8, bottom: 0 }}>
          <CartesianGrid stroke="var(--gridline)" horizontal={false} />
          <XAxis type="number" tick={{ fill: "var(--text-muted)", fontSize: 11 }} axisLine={{ stroke: "var(--axis)" }} />
          <YAxis
            type="category"
            dataKey="name"
            width={180}
            tick={{ fill: "var(--text-secondary)", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              background: "var(--surface-card)",
              border: "1px solid var(--border-hairline)",
              borderRadius: 6,
              fontSize: 12,
            }}
          />
          <Bar dataKey="contribution" radius={4} maxBarSize={16}>
            <LabelList
              dataKey="contribution"
              position="right"
              formatter={(v: unknown) => (typeof v === "number" ? v.toFixed(2) : "")}
              style={{ fill: "var(--text-secondary)", fontSize: 11 }}
            />
            {data.map((entry, i) => (
              <Cell
                key={i}
                fill={
                  entry.direction === "positive"
                    ? "var(--diverging-positive)"
                    : "var(--diverging-negative)"
                }
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Card>
  )
}
