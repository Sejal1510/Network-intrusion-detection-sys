"""Model-agnostic prediction: the single transform -> predict path shared by
every route (JSON `/predict`, CSV `/predict/batch`) and, per
nids.features.contracts's adapter pattern, any future input source (live
capture, PCAP flow extraction) that produces a DataFrame satisfying
FEATURE_COLUMNS.

Combines a required classifier run with an optional anomaly-detector run
(see `nids.api.model_loader.ServedEnsemble`) into one `PredictionResult`
per record. When no anomaly detector is served, `anomaly_score`/
`is_anomaly` are `None` and every other field is identical to
classifier-only (Milestone 2) behavior -- hybrid detection is additive,
never a behavior change for existing deployments.

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

from nids.api.model_loader import ServedEnsemble, ServedModel
from nids.api.severity import compute_severity


@dataclass(frozen=True)
class PredictionResult:
    prediction: Any
    probabilities: dict[str, float] | None
    confidence: float | None
    attack_category: str | None
    anomaly_score: float | None
    is_anomaly: bool | None
    severity: str


def _to_builtin(value: Any) -> Any:
    return value.item() if hasattr(value, "item") else value


def _is_attack(prediction: Any, label_column: str) -> bool:
    if label_column == "attack_category":
        return prediction != "normal"
    return bool(prediction)  # is_attack convention: 1 = attack, 0 = normal


def _attack_category(prediction: Any, label_column: str) -> str | None:
    return str(prediction) if label_column == "attack_category" else None


def _confidence(probabilities: dict[str, float] | None) -> float | None:
    return max(probabilities.values()) if probabilities else None


def _classify(
    classifier: ServedModel, df: pd.DataFrame
) -> tuple[list[Any], list[dict[str, float] | None]]:
    matrix = classifier.feature_engineer.transform(df)
    predictions = classifier.model.predict(matrix.X)

    if hasattr(classifier.model, "predict_proba"):
        proba = classifier.model.predict_proba(matrix.X)
        classes = classifier.model.classes_
        probabilities: list[dict[str, float] | None] = [
            {str(cls): float(p) for cls, p in zip(classes, row, strict=True)} for row in proba
        ]
    else:
        probabilities = [None] * len(predictions)

    return [_to_builtin(pred) for pred in predictions], probabilities


def _score_anomalies(
    anomaly_detector: ServedModel | None, df: pd.DataFrame, n: int
) -> tuple[list[float | None], list[bool | None]]:
    if anomaly_detector is None:
        return [None] * n, [None] * n

    matrix = anomaly_detector.feature_engineer.transform(df)
    scores = anomaly_detector.model.anomaly_score(matrix.X)
    # IsolationForestClassifier.predict: {1: anomaly/attack, 0: normal}
    flags = anomaly_detector.model.predict(matrix.X)
    return [float(s) for s in scores], [bool(f) for f in flags]


def _predict_dataframe(served_ensemble: ServedEnsemble, df: pd.DataFrame) -> list[PredictionResult]:
    classifier = served_ensemble.classifier
    label_column = classifier.metadata.get("label_column", "is_attack")

    predictions, probabilities = _classify(classifier, df)
    anomaly_scores, anomaly_flags = _score_anomalies(
        served_ensemble.anomaly_detector, df, len(predictions)
    )

    results = []
    for prediction, proba, anomaly_score, is_anomaly in zip(
        predictions, probabilities, anomaly_scores, anomaly_flags, strict=True
    ):
        confidence = _confidence(proba)
        results.append(
            PredictionResult(
                prediction=prediction,
                probabilities=proba,
                confidence=confidence,
                attack_category=_attack_category(prediction, label_column),
                anomaly_score=anomaly_score,
                is_anomaly=is_anomaly,
                severity=compute_severity(
                    _is_attack(prediction, label_column), confidence, is_anomaly
                ),
            )
        )
    return results


def predict_one(served_ensemble: ServedEnsemble, record: dict[str, Any]) -> PredictionResult:
    """Predict a single raw connection record (e.g. a JSON request body)."""
    return _predict_dataframe(served_ensemble, pd.DataFrame([record]))[0]


def predict_batch(served_ensemble: ServedEnsemble, df: pd.DataFrame) -> list[PredictionResult]:
    """Predict every row of a raw-record DataFrame (e.g. an uploaded CSV),
    in row order."""
    return _predict_dataframe(served_ensemble, df)
