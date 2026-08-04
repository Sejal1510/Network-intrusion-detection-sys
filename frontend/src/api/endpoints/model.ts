import { apiClient } from "@/api/client"
import type { ModelInfoResponse } from "@/api/types"

export function getModelInfo(): Promise<ModelInfoResponse> {
  return apiClient.get<ModelInfoResponse>("/model")
}
