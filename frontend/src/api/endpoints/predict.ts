import { apiClient } from "@/api/client"
import type { BatchPredictResponse, PredictRequest, PredictResponse } from "@/api/types"

export function predictOne(record: PredictRequest, explain: boolean): Promise<PredictResponse> {
  return apiClient.post<PredictResponse>(`/predict?explain=${explain}`, record)
}

export function predictBatch(file: File, explain: boolean): Promise<BatchPredictResponse> {
  const formData = new FormData()
  formData.append("file", file)
  return apiClient.post<BatchPredictResponse>(`/predict/batch?explain=${explain}`, formData)
}
