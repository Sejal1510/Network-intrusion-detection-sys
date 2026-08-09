import { useQuery } from "@tanstack/react-query"
import { listAuditEvents, type AuditEventFilters } from "@/api/endpoints/history"

export function useAuditEvents(filters: AuditEventFilters) {
  return useQuery({
    queryKey: ["audit", filters],
    queryFn: () => listAuditEvents(filters),
  })
}
