import { useHealth } from "@/hooks/useHealth"

/**
 * Shown on pages that need a database (Live Feed/Alerts/History) when the
 * server was started without --database-url. Those pages 503 on every
 * request in that case (see docs/API.md) -- this banner explains why
 * up front instead of letting each request fail silently confusing.
 */
export function DegradedModeBanner() {
  const { data: health } = useHealth()
  if (!health || health.database_configured) return null

  return (
    <div
      className="rounded-lg border p-3 text-sm"
      style={{ borderColor: "var(--status-warning)", color: "var(--text-primary)" }}
      role="status"
    >
      <span className="font-medium">Running without persistence.</span> This server was started
      without <code>--database-url</code>, so live streaming, alerts, and history are
      unavailable. Manual Predict and CSV Upload still work.
    </div>
  )
}
