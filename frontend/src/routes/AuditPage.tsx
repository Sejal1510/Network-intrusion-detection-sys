import { useSearchParams } from "react-router-dom"
import { DegradedModeBanner } from "@/components/layout/DegradedModeBanner"
import { Pagination } from "@/components/common/Pagination"
import { LoadingSkeleton } from "@/components/common/LoadingSkeleton"
import { ErrorState } from "@/components/common/ErrorState"
import { EmptyState } from "@/components/common/EmptyState"
import { useAuditEvents } from "@/hooks/useAuditEvents"

const LIMIT = 20

const EVENT_TYPES = [
  "login_succeeded",
  "login_failed",
  "logout",
  "device_paired",
  "device_pair_failed",
  "device_revoked",
  "alert_acknowledged",
]

export function AuditPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const eventType = searchParams.get("event_type") ?? ""
  const actor = searchParams.get("actor") ?? ""
  const offset = Number(searchParams.get("offset") ?? 0)

  const { data, isLoading, isError } = useAuditEvents({
    event_type: eventType || undefined,
    actor: actor || undefined,
    limit: LIMIT,
    offset,
  })

  function updateParam(key: string, value: string) {
    const next = new URLSearchParams(searchParams)
    if (value) next.set(key, value)
    else next.delete(key)
    next.delete("offset")
    setSearchParams(next)
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-[var(--text-primary)]">Audit Log</h2>
      <p className="text-sm text-[var(--text-secondary)]">
        Every security-relevant action recorded by the server: logins, device pairing/revocation,
        alert acknowledgements.
      </p>
      <DegradedModeBanner />

      <div className="flex flex-wrap gap-3 text-sm">
        <select
          value={eventType}
          onChange={(e) => updateParam("event_type", e.target.value)}
          className="rounded border border-[var(--border-hairline)] bg-[var(--surface-card)] px-2 py-1"
        >
          <option value="">All event types</option>
          {EVENT_TYPES.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </select>
        <input
          type="text"
          value={actor}
          onChange={(e) => updateParam("actor", e.target.value)}
          placeholder="Filter by actor (e.g. user:analyst1)"
          className="rounded border border-[var(--border-hairline)] bg-[var(--surface-card)] px-2 py-1"
        />
      </div>

      {isLoading && <LoadingSkeleton rows={5} />}
      {isError && <ErrorState message="Could not load the audit log. Is the server reachable?" />}
      {data && data.items.length === 0 && <EmptyState message="No audit events match these filters." />}
      {data && data.items.length > 0 && (
        <>
          <div className="overflow-x-auto rounded-lg border border-[var(--border-hairline)]">
            <table className="w-full text-left text-sm">
              <thead className="text-[var(--text-secondary)]">
                <tr className="border-b border-[var(--border-hairline)]">
                  <th className="px-3 py-2 font-medium">Time</th>
                  <th className="px-3 py-2 font-medium">Event</th>
                  <th className="px-3 py-2 font-medium">Actor</th>
                  <th className="px-3 py-2 font-medium">Target</th>
                  <th className="px-3 py-2 font-medium">Detail</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((event) => (
                  <tr key={event.id} className="data-row border-b border-[var(--border-hairline)] last:border-0">
                    <td className="px-3 py-2 text-[var(--text-secondary)]">
                      {new Date(event.created_at).toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-[var(--text-primary)]">{event.event_type}</td>
                    <td className="px-3 py-2 text-[var(--text-secondary)]">{event.actor}</td>
                    <td className="px-3 py-2 text-[var(--text-muted)]">{event.target_id ?? "—"}</td>
                    <td className="px-3 py-2 text-[var(--text-muted)]">{event.detail ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            offset={data.offset}
            limit={data.limit}
            total={data.total}
            onOffsetChange={(next) => {
              const params = new URLSearchParams(searchParams)
              params.set("offset", String(next))
              setSearchParams(params)
            }}
          />
        </>
      )}
    </div>
  )
}
