/**
 * Hand-written TS mirrors of src/nids/api/schemas.py. Kept in one file,
 * field-for-field, so a backend schema change has exactly one frontend
 * file to update to match.
 */

export type Severity = "low" | "medium" | "high" | "critical"

export interface FeatureContribution {
  feature: string
  value: unknown
  contribution: number
  direction: "positive" | "negative"
}

export interface Explanation {
  base_value: number
  top_features: FeatureContribution[]
  summary: string
}

export interface MitreTechnique {
  id: string
  name: string
  url: string
}

export interface MitreMapping {
  tactic: string
  techniques: MitreTechnique[]
}

export interface RiskScore {
  score: number
  severity: Severity
  /** Keys vary: "anomaly" is absent when no anomaly detector is served. */
  factors: Record<string, number>
}

export interface PredictResponse {
  prediction: string | number
  probabilities: Record<string, number> | null
  confidence: number | null
  attack_category: string | null
  anomaly_score: number | null
  is_anomaly: boolean | null
  severity: Severity
  explanation: Explanation | null
  risk_score: RiskScore
  mitre: MitreMapping | null
  alert_id: string | null
}

export interface BatchPredictSummary {
  total_records: number
  prediction_counts: Record<string, number>
}

export interface BatchPredictResponse {
  summary: BatchPredictSummary
  results: PredictResponse[]
}

export interface HealthResponse {
  status: string
  model_loaded: boolean
  database_configured: boolean
}

export interface ServedRunInfo {
  run_id: string
  model_name: string
  metrics: Record<string, unknown>
  metadata: Record<string, unknown>
}

export interface ModelInfoResponse {
  run_id: string
  model_name: string
  label_column: string | null
  metrics: Record<string, unknown>
  metadata: Record<string, unknown>
  anomaly_detector: ServedRunInfo | null
}

export interface PredictionHistoryItem {
  id: string
  created_at: string
  run_id: string
  anomaly_run_id: string | null
  label_column: string
  prediction: string
  probabilities: Record<string, number> | null
  confidence: number | null
  attack_category: string | null
  anomaly_score: number | null
  is_anomaly: boolean | null
  severity: Severity
  risk_score: number
  risk_factors: Record<string, number>
  mitre: MitreMapping | null
  raw_record: Record<string, unknown>
  source: string
  explanation: Explanation | null
}

export interface PredictionHistoryResponse {
  items: PredictionHistoryItem[]
  total: number
  limit: number
  offset: number
}

export interface AlertHistoryItem {
  id: string
  prediction_id: string
  created_at: string
  level: Severity
  title: string
  message: string
  risk_score: number
  attack_category: string | null
  mitre: MitreMapping | null
  acknowledged: boolean
  source: string
}

export interface AlertHistoryResponse {
  items: AlertHistoryItem[]
  total: number
  limit: number
  offset: number
}

export interface PairingTokenResponse {
  pairing_token: string
  expires_in_seconds: number
}

export interface DeviceCredentialResponse {
  device_id: string
  token: string
}

/** One raw connection record -- the 41 fields of nids.data.schema.FEATURE_COLUMNS. */
export type PredictRequest = Record<string, string | number>

/** A live prediction pushed over /ws/live. */
export interface LiveFeedMessage {
  type: "prediction"
  data: PredictResponse
}
