import { useQuery } from "@tanstack/react-query"
import { listPredictions, type PredictionHistoryFilters } from "@/api/endpoints/history"

export function usePredictionHistory(filters: PredictionHistoryFilters) {
  return useQuery({
    queryKey: ["predictions", filters],
    queryFn: () => listPredictions(filters),
  })
}
