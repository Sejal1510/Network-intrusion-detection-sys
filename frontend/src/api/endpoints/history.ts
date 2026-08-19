import { apiClient } from "@/api/client"
import type {
  AlertHistoryResponse,
  AuditEventResponse,
  EnrichmentListResponse,
  PredictionHistoryResponse,
} from "@/api/types"

function toQueryString(params: object): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params) as [string, string | number | boolean | undefined][]) {
    if (value !== undefined && value !== "") search.set(key, String(value))
  }
  const query = search.toString()
  return query ? `?${query}` : ""
}

export interface PredictionHistoryFilters {
  severity?: string
  attack_category?: string
  min_risk_score?: number
  start_date?: string
  end_date?: string
  limit?: number
  offset?: number
}

export function listPredictions(
  filters: PredictionHistoryFilters
): Promise<PredictionHistoryResponse> {
  return apiClient.get<PredictionHistoryResponse>(
    `/history/predictions${toQueryString(filters)}`
  )
}

export interface AlertHistoryFilters {
  level?: string
  acknowledged?: boolean
  start_date?: string
  end_date?: string
  limit?: number
  offset?: number
}

export function listAlerts(filters: AlertHistoryFilters): Promise<AlertHistoryResponse> {
  return apiClient.get<AlertHistoryResponse>(`/history/alerts${toQueryString(filters)}`)
}

export function acknowledgeAlert(alertId: string) {
  return apiClient.post(`/history/alerts/${alertId}/acknowledge`)
}

export function getAlertEnrichment(alertId: string): Promise<EnrichmentListResponse> {
  return apiClient.get<EnrichmentListResponse>(`/history/alerts/${alertId}/enrichment`)
}

export interface AuditEventFilters {
  event_type?: string
  actor?: string
  start_date?: string
  end_date?: string
  limit?: number
  offset?: number
}

export function listAuditEvents(filters: AuditEventFilters): Promise<AuditEventResponse> {
  return apiClient.get<AuditEventResponse>(`/history/audit${toQueryString(filters)}`)
}
