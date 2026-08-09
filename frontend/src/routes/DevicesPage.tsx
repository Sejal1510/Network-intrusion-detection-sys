import { useSearchParams } from "react-router-dom"
import { LoadingSkeleton } from "@/components/common/LoadingSkeleton"
import { ErrorState } from "@/components/common/ErrorState"
import { EmptyState } from "@/components/common/EmptyState"
import { Pagination } from "@/components/common/Pagination"
import { useDevices } from "@/hooks/useDevices"
import { useRevokeDevice } from "@/hooks/useRevokeDevice"

const LIMIT = 20

/** Status chip mirroring SeverityBadge's pill formula -- shape (check vs. cross), not just color, carries the distinction. */
function DeviceStatus({ revoked }: { revoked: boolean }) {
  const colorVar = revoked ? "--status-critical" : "--status-good"
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium"
      style={{
        color: `var(${colorVar})`,
        borderColor: `var(${colorVar})`,
        backgroundColor: `color-mix(in srgb, var(${colorVar}) 12%, transparent)`,
      }}
    >
      {revoked ? (
        <svg viewBox="0 0 16 16" width="12" height="12" fill="none" aria-hidden="true">
          <path d="M4.5 4.5l7 7M11.5 4.5l-7 7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      ) : (
        <svg viewBox="0 0 16 16" width="12" height="12" fill="none" aria-hidden="true">
          <path d="M3 8.5l3 3 7-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
      {revoked ? "Revoked" : "Active"}
    </span>
  )
}

export function DevicesPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const offset = Number(searchParams.get("offset") ?? 0)

  const { data, isLoading, isError } = useDevices({ limit: LIMIT, offset })
  const revoke = useRevokeDevice()

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-[var(--text-primary)]">Devices</h2>
      <p className="text-sm text-[var(--text-secondary)]">
        Devices paired with this dashboard via the live-capture agent. Revoking a device
        immediately invalidates its token.
      </p>

      {isLoading && <LoadingSkeleton rows={5} />}
      {isError && <ErrorState message="Could not load devices. Is the server reachable?" />}
      {data && data.items.length === 0 && <EmptyState message="No devices paired yet." />}
      {data && data.items.length > 0 && (
        <>
          <div className="overflow-x-auto rounded-lg border border-[var(--border-hairline)]">
            <table className="w-full text-left text-sm">
              <thead className="text-[var(--text-secondary)]">
                <tr className="border-b border-[var(--border-hairline)]">
                  <th className="px-3 py-2 font-medium">Name</th>
                  <th className="px-3 py-2 font-medium">Paired at</th>
                  <th className="px-3 py-2 font-medium">Last seen</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium" />
                </tr>
              </thead>
              <tbody>
                {data.items.map((device) => (
                  <tr key={device.id} className="data-row border-b border-[var(--border-hairline)] last:border-0">
                    <td className="px-3 py-2 text-[var(--text-primary)]">{device.name}</td>
                    <td className="px-3 py-2 text-[var(--text-secondary)]">{device.paired_at}</td>
                    <td className="px-3 py-2 text-[var(--text-secondary)]">
                      {device.last_seen_at ?? "Never"}
                    </td>
                    <td className="px-3 py-2">
                      <DeviceStatus revoked={device.revoked} />
                    </td>
                    <td className="px-3 py-2 text-right">
                      {!device.revoked && (
                        <button
                          type="button"
                          onClick={() => revoke.mutate(device.id)}
                          disabled={revoke.isPending && revoke.variables === device.id}
                          className="rounded border border-[var(--border-hairline)] px-2 py-1 text-xs transition-colors hover:border-[color-mix(in_srgb,var(--status-critical)_40%,transparent)] hover:text-[var(--status-critical)] disabled:opacity-40"
                        >
                          Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {revoke.isError && (
            <ErrorState
              message={revoke.error instanceof Error ? revoke.error.message : "Revoke failed."}
            />
          )}
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
