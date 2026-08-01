"""Pydantic request/response schemas for the inference API.

`PredictRequest`'s fields are generated once from
`nids.data.schema.FEATURE_COLUMNS`/`CATEGORICAL_COLUMNS` rather than
hand-duplicated, so the 41-column raw-record contract has exactly one
source of truth (`nids.data.schema`) instead of a second, hand-maintained
list here that can silently drift out of sync.
"""

from __future__ import annotations

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
