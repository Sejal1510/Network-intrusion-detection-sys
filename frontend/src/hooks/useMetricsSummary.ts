import { useQuery } from "@tanstack/react-query"
import { getMetricsSummary } from "@/api/endpoints/metrics"

export function useMetricsSummary() {
  return useQuery({
    queryKey: ["metrics-summary"],
    queryFn: getMetricsSummary,
    refetchInterval: 15_000,
  })
}
