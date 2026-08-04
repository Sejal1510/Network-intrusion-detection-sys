import { apiClient } from "@/api/client"
import type { MitreMapping } from "@/api/types"

export function getMitreMappings(): Promise<Record<string, MitreMapping>> {
  return apiClient.get<Record<string, MitreMapping>>("/mitre")
}
