import { useSearchParams } from "react-router-dom"
import { DegradedModeBanner } from "@/components/layout/DegradedModeBanner"
import { Pagination } from "@/components/common/Pagination"
import { FilterSelect } from "@/components/common/FilterSelect"
import { TableSkeleton } from "@/components/common/TableSkeleton"
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

  const hasActiveFilters = Boolean(eventType || actor)

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

  function clearFilters() {
    const next = new URLSearchParams(searchParams)
    next.delete("event_type")
    next.delete("actor")
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

      <div className="flex flex-wrap items-center gap-3 text-sm">
        <FilterSelect
          aria-label="Filter by event type"
          value={eventType}
          onChange={(e) => updateParam("event_type", e.target.value)}
        >
          <option value="">All event types</option>
          {EVENT_TYPES.map((type) => (
            <option key={type} value={type}>
              {type}
            </option>
          ))}
        </FilterSelect>
        <input
          type="text"
          value={actor}
          onChange={(e) => updateParam("actor", e.target.value)}
          placeholder="Filter by actor (e.g. user:analyst1)"
          className="rounded border border-[var(--border-hairline)] bg-[var(--surface-card)] px-2 py-1 text-sm text-[var(--text-primary)] transition-colors placeholder:text-[var(--text-muted)] hover:border-[color-mix(in_srgb,var(--accent)_35%,var(--border-hairline))]"
        />
        {hasActiveFilters && (
          <button
            type="button"
            onClick={clearFilters}
            className="text-xs text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
          >
            Clear filters
          </button>
        )}
      </div>

      {isLoading && <TableSkeleton rows={5} columns={5} />}
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
