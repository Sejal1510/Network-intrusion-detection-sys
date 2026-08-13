import { useSearchParams } from "react-router-dom"
import { DegradedModeBanner } from "@/components/layout/DegradedModeBanner"
import { PredictionTable } from "@/components/tables/PredictionTable"
import { Pagination } from "@/components/common/Pagination"
import { FilterSelect } from "@/components/common/FilterSelect"
import { TableSkeleton } from "@/components/common/TableSkeleton"
import { ErrorState } from "@/components/common/ErrorState"
import { usePredictionHistory } from "@/hooks/usePredictionHistory"

const LIMIT = 20

export function HistoryPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const severity = searchParams.get("severity") ?? ""
  const attackCategory = searchParams.get("attack_category") ?? ""
  const offset = Number(searchParams.get("offset") ?? 0)
  const hasActiveFilters = Boolean(severity || attackCategory)

  const { data, isLoading, isError } = usePredictionHistory({
    severity: severity || undefined,
    attack_category: attackCategory || undefined,
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
    next.delete("severity")
    next.delete("attack_category")
    next.delete("offset")
    setSearchParams(next)
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-[var(--text-primary)]">Prediction History</h2>
      <DegradedModeBanner />

      <div className="flex flex-wrap items-center gap-3 text-sm">
        <FilterSelect
          aria-label="Filter by severity"
          value={severity}
          onChange={(e) => updateParam("severity", e.target.value)}
        >
          <option value="">All severities</option>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
          <option value="critical">Critical</option>
        </FilterSelect>
        <FilterSelect
          aria-label="Filter by attack category"
          value={attackCategory}
          onChange={(e) => updateParam("attack_category", e.target.value)}
        >
          <option value="">All categories</option>
          <option value="normal">Normal</option>
          <option value="dos">DoS</option>
          <option value="probe">Probe</option>
          <option value="r2l">R2L</option>
          <option value="u2r">U2R</option>
        </FilterSelect>
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

      {isLoading && <TableSkeleton rows={5} columns={6} />}
      {isError && <ErrorState message="Could not load history. Is the server reachable?" />}
      {data && (
        <>
          <PredictionTable items={data.items} />
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
