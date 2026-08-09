import type { ReactNode } from "react"
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { StatTile } from "@/components/common/StatTile"
import { LoadingSkeleton } from "@/components/common/LoadingSkeleton"
import { ErrorState } from "@/components/common/ErrorState"
import { EmptyState } from "@/components/common/EmptyState"
import { useMetricsSummary } from "@/hooks/useMetricsSummary"
import { titleCase } from "@/lib/format"

function ChartCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-card)] p-4">
      <h3 className="mb-2 text-sm font-medium text-[var(--text-primary)]">{title}</h3>
      {children}
    </div>
  )
}

export function MetricsPage() {
  const { data, isLoading, isError } = useMetricsSummary()

  const alertsData = data
    ? Object.entries(data.alerts_by_source).map(([source, count]) => ({
        source: titleCase(source),
        count,
      }))
    : []

  const notificationsData = data
    ? Object.entries(data.notifications_by_channel).flatMap(([channel, byStatus]) =>
        Object.entries(byStatus).map(([status, count]) => ({ channel, status, count }))
      )
    : []
  const notificationChannels = [...new Set(notificationsData.map((d) => d.channel))]
  const notificationChartData = notificationChannels.map((channel) => {
    const row: Record<string, string | number> = { channel }
    for (const { channel: c, status, count } of notificationsData) {
      if (c === channel) row[status] = count
    }
    return row
  })

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-[var(--text-primary)]">Metrics</h2>
      <p className="text-sm text-[var(--text-secondary)]">
        A live read of this server's own operational counters (see{" "}
        <code className="text-xs">GET /metrics</code> for the full Prometheus scrape).
      </p>

      {isLoading && <LoadingSkeleton rows={5} />}
      {isError && <ErrorState message="Could not load metrics. Is the server reachable?" />}

      {data && (
        <>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <StatTile label="HTTP requests" value={data.http_requests_total} />
            {Object.entries(data.predictions_by_route).map(([route, count]) => (
              <StatTile key={route} label={`Predictions via ${route}`} value={count} />
            ))}
            {Object.entries(data.avg_prediction_duration_seconds).map(([route, seconds]) => (
              <StatTile
                key={route}
                label={`Avg latency ${route}`}
                value={`${(seconds * 1000).toFixed(0)}ms`}
              />
            ))}
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard title="Alerts raised by source">
              {alertsData.length === 0 ? (
                <EmptyState message="No alerts raised yet." />
              ) : (
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={alertsData} margin={{ top: 16, right: 8, left: 8, bottom: 0 }}>
                    <XAxis
                      dataKey="source"
                      tickLine={false}
                      axisLine={{ stroke: "var(--axis)" }}
                      tick={{ fill: "var(--text-muted)", fontSize: 12 }}
                    />
                    <YAxis hide />
                    <Tooltip
                      cursor={{ fill: "var(--gridline)" }}
                      contentStyle={{
                        background: "var(--surface-card)",
                        border: "1px solid var(--border-hairline)",
                        borderRadius: 6,
                        fontSize: 12,
                      }}
                    />
                    <Bar dataKey="count" fill="var(--status-serious)" radius={[4, 4, 0, 0]} maxBarSize={48} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </ChartCard>

            <ChartCard title="Notification delivery by channel">
              {notificationChartData.length === 0 ? (
                <EmptyState message="No notifications sent yet (no channel configured, or nothing has alerted)." />
              ) : (
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={notificationChartData} margin={{ top: 16, right: 8, left: 8, bottom: 0 }}>
                    <CartesianGrid stroke="var(--gridline)" vertical={false} />
                    <XAxis
                      dataKey="channel"
                      tickLine={false}
                      axisLine={{ stroke: "var(--axis)" }}
                      tick={{ fill: "var(--text-muted)", fontSize: 11 }}
                    />
                    <YAxis hide />
                    <Tooltip
                      cursor={{ fill: "var(--gridline)" }}
                      contentStyle={{
                        background: "var(--surface-card)",
                        border: "1px solid var(--border-hairline)",
                        borderRadius: 6,
                        fontSize: 12,
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="success" fill="var(--status-good)" radius={[4, 4, 0, 0]} maxBarSize={32} />
                    <Bar dataKey="failure" fill="var(--status-critical)" radius={[4, 4, 0, 0]} maxBarSize={32} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </ChartCard>
          </div>
        </>
      )}
    </div>
  )
}
