import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { Card } from "@/components/common/Card"
import type { LiveFeedEntry } from "@/hooks/useLiveFeed"

const BUCKET_COUNT = 20

interface Bucket {
  label: string
  count: number
  alerts: number | null
}

function bucketEntries(entries: LiveFeedEntry[]): Bucket[] {
  if (entries.length === 0) return []

  // entries arrive newest-first; work chronologically for the timeline
  const chronological = [...entries].reverse()
  const first = new Date(chronological[0].created_at).getTime()
  const last = new Date(chronological[chronological.length - 1].created_at).getTime()
  const span = Math.max(1, last - first)
  const bucketSize = span / BUCKET_COUNT

  const buckets: Bucket[] = Array.from({ length: BUCKET_COUNT }, (_, i) => ({
    label: new Date(first + i * bucketSize).toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    }),
    count: 0,
    alerts: null,
  }))

  for (const entry of chronological) {
    const t = new Date(entry.created_at).getTime()
    const index = Math.min(BUCKET_COUNT - 1, Math.floor((t - first) / bucketSize))
    buckets[index].count += 1
    if (entry.alert_id) buckets[index].alerts = (buckets[index].alerts ?? 0) + 1
  }

  return buckets
}

export function PredictionsOverTimeChart({ entries }: { entries: LiveFeedEntry[] }) {
  const data = bucketEntries(entries)

  return (
    <Card>
      <h3 className="mb-2 text-sm font-medium text-[var(--text-primary)]">Predictions over time</h3>
      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--gridline)" vertical={false} />
          <XAxis
            dataKey="label"
            tickLine={false}
            axisLine={{ stroke: "var(--axis)" }}
            tick={{ fill: "var(--text-muted)", fontSize: 11 }}
            interval="preserveStartEnd"
          />
          <YAxis
            tickLine={false}
            axisLine={false}
            tick={{ fill: "var(--text-muted)", fontSize: 11 }}
            allowDecimals={false}
          />
          <Tooltip
            cursor={{ stroke: "var(--accent)", strokeWidth: 1, strokeDasharray: "3 3" }}
            contentStyle={{
              background: "var(--surface-elevated)",
              border: "1px solid var(--border-hairline)",
              borderRadius: 8,
              fontSize: 12,
              boxShadow: "var(--shadow-rest)",
            }}
            labelStyle={{ color: "var(--text-primary)", fontWeight: 600, marginBottom: 2 }}
            itemStyle={{ color: "var(--text-secondary)" }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Area
            type="monotone"
            dataKey="count"
            name="Predictions"
            stroke="var(--sequential-450)"
            fill="var(--sequential-450)"
            fillOpacity={0.18}
            strokeWidth={2}
            activeDot={{ r: 4, fill: "var(--accent)", stroke: "var(--surface-card)", strokeWidth: 2 }}
          />
          <Scatter dataKey="alerts" name="Alerts" fill="var(--status-critical)" />
        </ComposedChart>
      </ResponsiveContainer>
    </Card>
  )
}
