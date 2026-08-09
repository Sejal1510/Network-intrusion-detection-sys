import { useQuery } from "@tanstack/react-query"
import { getRules } from "@/api/endpoints/rules"

export function useRules() {
  return useQuery({
    queryKey: ["rules"],
    queryFn: getRules,
    staleTime: 60_000,
  })
}
