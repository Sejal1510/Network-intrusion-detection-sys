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


class PredictResponse(BaseModel):
    prediction: Any
    probabilities: dict[str, float] | None = None


class BatchPredictSummary(BaseModel):
    total_records: int
    prediction_counts: dict[str, int]


class BatchPredictResponse(BaseModel):
    summary: BatchPredictSummary
    results: list[PredictResponse]


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool


class ModelInfoResponse(BaseModel):
    run_id: str
    model_name: str
    label_column: str | None = None
    metrics: dict[str, Any]
    metadata: dict[str, Any]
