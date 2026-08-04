import { useSearchParams } from "react-router-dom"
import { DegradedModeBanner } from "@/components/layout/DegradedModeBanner"
import { AlertTable } from "@/components/tables/AlertTable"
import { Pagination } from "@/components/common/Pagination"
import { LoadingSkeleton } from "@/components/common/LoadingSkeleton"
import { ErrorState } from "@/components/common/ErrorState"
import { useAlerts } from "@/hooks/useAlerts"

const LIMIT = 20

export function AlertsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const level = searchParams.get("level") ?? ""
  const acknowledged = searchParams.get("acknowledged") ?? ""
  const offset = Number(searchParams.get("offset") ?? 0)

  const { data, isLoading, isError } = useAlerts({
    level: level || undefined,
    acknowledged: acknowledged === "" ? undefined : acknowledged === "true",
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
      <h2 className="text-lg font-semibold text-[var(--text-primary)]">Alerts</h2>
      <DegradedModeBanner />

      <div className="flex flex-wrap gap-3 text-sm">
        <select
          value={level}
          onChange={(e) => updateParam("level", e.target.value)}
          className="rounded border border-[var(--border-hairline)] bg-[var(--surface-card)] px-2 py-1"
        >
          <option value="">All severities</option>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
          <option value="critical">Critical</option>
        </select>
        <select
          value={acknowledged}
          onChange={(e) => updateParam("acknowledged", e.target.value)}
          className="rounded border border-[var(--border-hairline)] bg-[var(--surface-card)] px-2 py-1"
        >
          <option value="">All statuses</option>
          <option value="false">Unacknowledged</option>
          <option value="true">Acknowledged</option>
        </select>
      </div>

      {isLoading && <LoadingSkeleton rows={5} />}
      {isError && <ErrorState message="Could not load alerts. Is the server reachable?" />}
      {data && (
        <>
          <AlertTable alerts={data.items} />
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
