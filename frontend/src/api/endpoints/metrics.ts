import { apiClient } from "@/api/client"
import type { MetricsSummary } from "@/api/types"

export function getMetricsSummary(): Promise<MetricsSummary> {
  return apiClient.get<MetricsSummary>("/metrics/summary")
}
