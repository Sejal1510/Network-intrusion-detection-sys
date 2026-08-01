"""Model-agnostic prediction: the single transform -> predict path shared by
every route (JSON `/predict`, CSV `/predict/batch`) and, per
nids.features.contracts's adapter pattern, any future input source (live
capture, PCAP flow extraction) that produces a DataFrame satisfying
FEATURE_COLUMNS.

Deliberately free of HTTP/FastAPI/Pydantic imports -- this module doesn't
know it's being served over HTTP, exactly like nids.training.core doesn't
know it's being driven by a CLI. `ValueError` (raised by
`FeatureEngineer.transform` via `validate_raw_records` for a malformed
record) is left to propagate; the API layer maps it to HTTP 400.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from nids.api.model_loader import ServedModel


@dataclass(frozen=True)
class PredictionResult:
    prediction: Any
    probabilities: dict[str, float] | None


def _to_builtin(value: Any) -> Any:
    return value.item() if hasattr(value, "item") else value


def _predict_dataframe(served_model: ServedModel, df: pd.DataFrame) -> list[PredictionResult]:
    matrix = served_model.feature_engineer.transform(df)
    predictions = served_model.model.predict(matrix.X)

    if hasattr(served_model.model, "predict_proba"):
        proba = served_model.model.predict_proba(matrix.X)
        classes = served_model.model.classes_
        probabilities: list[dict[str, float] | None] = [
            {str(cls): float(p) for cls, p in zip(classes, row, strict=True)} for row in proba
        ]
    else:
        probabilities = [None] * len(predictions)

    return [
        PredictionResult(prediction=_to_builtin(pred), probabilities=proba_row)
        for pred, proba_row in zip(predictions, probabilities, strict=True)
    ]


def predict_one(served_model: ServedModel, record: dict[str, Any]) -> PredictionResult:
    """Predict a single raw connection record (e.g. a JSON request body)."""
    return _predict_dataframe(served_model, pd.DataFrame([record]))[0]


def predict_batch(served_model: ServedModel, df: pd.DataFrame) -> list[PredictionResult]:
    """Predict every row of a raw-record DataFrame (e.g. an uploaded CSV),
    in row order."""
    return _predict_dataframe(served_model, df)
