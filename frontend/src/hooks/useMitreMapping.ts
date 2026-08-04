import { useQuery } from "@tanstack/react-query"
import { getMitreMappings } from "@/api/endpoints/mitre"

export function useMitreMapping() {
  return useQuery({
    queryKey: ["mitre"],
    queryFn: getMitreMappings,
    staleTime: Infinity,
  })
}
