"""Pydantic request/response schemas for the inference API.

`PredictRequest`'s fields are generated once from
`nids.data.schema.FEATURE_COLUMNS`/`CATEGORICAL_COLUMNS` rather than
hand-duplicated, so the 41-column raw-record contract has exactly one
source of truth (`nids.data.schema`) instead of a second, hand-maintained
list here that can silently drift out of sync.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, create_model

from nids.data.schema import CATEGORICAL_COLUMNS, FEATURE_COLUMNS

PredictRequest = create_model(
    "PredictRequest",
    __config__=ConfigDict(extra="forbid"),
    **{
        column: (str if column in CATEGORICAL_COLUMNS else float, ...)
        for column in FEATURE_COLUMNS
    },
)
"""One raw connection record -- field-for-field, `nids.data.schema.FEATURE_COLUMNS`."""


class FeatureContributionResponse(BaseModel):
    feature: str
    value: Any
    contribution: float
    direction: str


class ExplanationResponse(BaseModel):
    base_value: float
    top_features: list[FeatureContributionResponse]
    summary: str


class MitreTechniqueResponse(BaseModel):
    id: str
    name: str
    url: str


class MitreMappingResponse(BaseModel):
    tactic: str
    techniques: list[MitreTechniqueResponse]


class RiskScoreResponse(BaseModel):
    score: float
    severity: str
    factors: dict[str, float]


class PredictResponse(BaseModel):
    prediction: Any
    probabilities: dict[str, float] | None = None
    confidence: float | None = None
    attack_category: str | None = None
    anomaly_score: float | None = None
    is_anomaly: bool | None = None
    severity: str
    explanation: ExplanationResponse | None = None
    risk_score: RiskScoreResponse
    mitre: MitreMappingResponse | None = None
    alert_id: str | None = None


class BatchPredictSummary(BaseModel):
    total_records: int
    prediction_counts: dict[str, int]


class BatchPredictResponse(BaseModel):
    summary: BatchPredictSummary
    results: list[PredictResponse]


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    database_configured: bool


class ServedRunInfo(BaseModel):
    run_id: str
    model_name: str
    metrics: dict[str, Any]
    metadata: dict[str, Any]


class ModelInfoResponse(BaseModel):
    run_id: str
    model_name: str
    label_column: str | None = None
    metrics: dict[str, Any]
    metadata: dict[str, Any]
    anomaly_detector: ServedRunInfo | None = None


class PredictionHistoryItem(BaseModel):
    id: str
    created_at: datetime
    run_id: str
    anomaly_run_id: str | None
    label_column: str
    prediction: str
    probabilities: dict[str, float] | None
    confidence: float | None
    attack_category: str | None
    anomaly_score: float | None
    is_anomaly: bool | None
    severity: str
    risk_score: float
    risk_factors: dict[str, float]
    mitre: dict[str, Any] | None
    raw_record: dict[str, Any]
    source: str
    explanation: dict[str, Any] | None


class PredictionHistoryResponse(BaseModel):
    items: list[PredictionHistoryItem]
    total: int
    limit: int
    offset: int


class AlertHistoryItem(BaseModel):
    id: str
    prediction_id: str
    created_at: datetime
    level: str
    title: str
    message: str
    risk_score: float
    attack_category: str | None
    mitre: dict[str, Any] | None
    acknowledged: bool
    source: str


class AlertHistoryResponse(BaseModel):
    items: list[AlertHistoryItem]
    total: int
    limit: int
    offset: int


class AuditEventItem(BaseModel):
    id: str
    created_at: datetime
    event_type: str
    actor: str
    target_id: str | None
    detail: str | None


class AuditEventResponse(BaseModel):
    items: list[AuditEventItem]
    total: int
    limit: int
    offset: int


class PairingTokenResponse(BaseModel):
    pairing_token: str
    expires_in_seconds: int


class PairingExchangeRequest(BaseModel):
    pairing_token: str
    device_name: str


class DeviceCredentialResponse(BaseModel):
    device_id: str
    token: str


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    role: str


class CurrentUserResponse(BaseModel):
    username: str
    role: str


class WsTicketResponse(BaseModel):
    ticket: str
    expires_in_seconds: int


class DeviceListItem(BaseModel):
    id: str
    name: str
    user_id: str | None
    paired_at: datetime
    last_seen_at: datetime | None
    revoked: bool


class DeviceListResponse(BaseModel):
    items: list[DeviceListItem]
    total: int
    limit: int
    offset: int


class RuleConditionResponse(BaseModel):
    field: str
    operator: str
    value: Any


class RuleResponse(BaseModel):
    id: str
    name: str
    description: str
    severity: str
    conditions: list[RuleConditionResponse]
    mitre: MitreMappingResponse | None


class MetricsSummaryResponse(BaseModel):
    http_requests_total: float
    alerts_by_source: dict[str, float]
    notifications_by_channel: dict[str, dict[str, float]]
    predictions_by_route: dict[str, float]
    avg_prediction_duration_seconds: dict[str, float]
