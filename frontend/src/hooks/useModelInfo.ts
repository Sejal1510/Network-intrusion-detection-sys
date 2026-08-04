import { useQuery } from "@tanstack/react-query"
import { getModelInfo } from "@/api/endpoints/model"

export function useModelInfo() {
  return useQuery({
    queryKey: ["model"],
    queryFn: getModelInfo,
    staleTime: 60_000,
  })
}
