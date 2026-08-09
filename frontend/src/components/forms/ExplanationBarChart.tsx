import { Bar, BarChart, Cell, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { Card } from "@/components/common/Card"
import type { Explanation } from "@/api/types"

interface ContributionLabelProps {
  x?: number | string
  y?: number | string
  width?: number | string
  height?: number | string
  value?: unknown
}

function toNumber(input: unknown): number | undefined {
  if (typeof input === "number") return input
  if (typeof input === "string" && input.trim() !== "") return Number(input)
  return undefined
}

/**
 * Recharts' built-in LabelList `position="right"` anchors to one edge of
 * the bar rectangle regardless of sign -- fine for positive contributions
 * (that edge is the far tip), but for negative contributions that same
 * edge sits at the zero baseline, right where the Y-axis category text
 * lives, so the two collide. This renders the value at whichever edge is
 * actually the bar's *tip* (computed via min/max of both edges, so it
 * doesn't depend on Recharts' x/width sign convention), always on the
 * side away from zero -- the same place a positive label already sat.
 */
function ContributionLabel(props: ContributionLabelProps) {
  const x = toNumber(props.x)
  const y = toNumber(props.y)
  const width = toNumber(props.width)
  const height = toNumber(props.height)
  const value = toNumber(props.value)
  if (x === undefined || y === undefined || width === undefined || height === undefined || value === undefined || Number.isNaN(value)) {
    return null
  }
  const edgeA = x
  const edgeB = x + width
  const isNegative = value < 0
  const tip = isNegative ? Math.min(edgeA, edgeB) : Math.max(edgeA, edgeB)
  const labelX = isNegative ? tip - 6 : tip + 6

  return (
    <text
      x={labelX}
      y={y + height / 2}
      dy={4}
      textAnchor={isNegative ? "end" : "start"}
      fill="var(--text-secondary)"
      fontSize={11}
    >
      {value.toFixed(2)}
    </text>
  )
}

export function ExplanationBarChart({ explanation }: { explanation: Explanation }) {
  const data = [...explanation.top_features]
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
    .map((f) => ({
      name: `${f.feature} = ${f.value}`,
      contribution: f.contribution,
      direction: f.direction,
    }))

  // Without explicit padding, Recharts' auto domain is exactly
  // [dataMin, dataMax] -- so whichever bar holds the most negative
  // contribution has its tip land exactly on the plot's left edge, the
  // same place the Y-axis category text sits, regardless of where its
  // label is anchored. Padding the domain guarantees every bar's tip
  // (and therefore its label) has room before that edge.
  const contributions = data.map((d) => d.contribution)
  const dataMin = Math.min(0, ...contributions)
  const dataMax = Math.max(0, ...contributions)
  const pad = Math.max((dataMax - dataMin) * 0.15, 0.01)
  const domain: [number, number] = [dataMin - pad, dataMax + pad]

  return (
    <Card>
      <h3 className="mb-1 text-sm font-medium text-[var(--text-primary)]">Why this prediction</h3>
      <p className="mb-3 text-xs text-[var(--text-secondary)]">{explanation.summary}</p>
      <ResponsiveContainer width="100%" height={Math.max(160, data.length * 28)}>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, left: 24, bottom: 0 }}>
          <CartesianGrid stroke="var(--gridline)" horizontal={false} />
          <XAxis
            type="number"
            domain={domain}
            tickFormatter={(v: unknown) => (typeof v === "number" ? v.toFixed(2) : String(v))}
            tick={{ fill: "var(--text-muted)", fontSize: 11 }}
            axisLine={{ stroke: "var(--axis)" }}
          />
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
            <LabelList dataKey="contribution" content={ContributionLabel} />
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
