import { apiClient } from "@/api/client"
import type { HealthResponse } from "@/api/types"

export function getHealth(): Promise<HealthResponse> {
  return apiClient.get<HealthResponse>("/health")
}
