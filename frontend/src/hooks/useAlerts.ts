import { useQuery } from "@tanstack/react-query"
import { listAlerts, type AlertHistoryFilters } from "@/api/endpoints/history"

export function useAlerts(filters: AlertHistoryFilters) {
  return useQuery({
    queryKey: ["alerts", filters],
    queryFn: () => listAlerts(filters),
  })
}
