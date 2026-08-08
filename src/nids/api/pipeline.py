"""Per-record pipeline orchestration: predict -> optional explain -> risk
-> mitre -> alert -> optional persist -> response. The one place this
orchestration lives -- extracted from `app.py`'s original inline
`/predict` route body (a pure refactor, not new logic) so the HTTP route,
`/predict/batch`, and the live worker (`nids.api.worker`, added later in
Milestone 6) all call the *same* code instead of each inlining a copy.

Two entry points:

- `finish_record(...)` -- given an already-computed prediction (and,
  optionally, explanation), runs risk/mitre/alert/persist/response-
  building. Used directly by `/predict/batch`, which computes predictions
  and explanations for the *whole* upload in one vectorized
  `predict_batch`/`explain_batch` call and then finishes each row --
  calling `process_record` per row there would silently lose that
  vectorization.
- `process_record(...)` -- `predict_one` + a conditional `explain_one`,
  then `finish_record`. Used by single-record callers: the HTTP
  `/predict` route and the live worker. The live worker's explain policy
  differs from `/predict`'s (`?explain=true` decided upfront): it
  explains only flows that turn out to be alert-worthy, not every flow --
  expressed via `explain` accepting a callable, not just a bool.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pandas as pd
from sqlalchemy.engine import Engine

from nids.api.alerts import Alert, generate_alert, meets_min_severity
from nids.api.config import ServingConfig
from nids.api.explain import Explanation, explain_one
from nids.api.inference import PredictionResult, predict_one
from nids.api.mitre import MitreMapping, map_to_mitre
from nids.api.model_loader import ServedEnsemble
from nids.api.risk import RiskScore, compute_risk_score
from nids.api.schemas import (
    ExplanationResponse,
    FeatureContributionResponse,
    MitreMappingResponse,
    MitreTechniqueResponse,
    PredictResponse,
    RiskScoreResponse,
)
from nids.api.store import save_alert, save_prediction

# A plain bool (decided upfront, e.g. `/predict`'s `?explain=true`) or a
# callable that decides given the prediction and its risk score (e.g.
# "only if this will be alert-worthy" -- see nids.api.worker).
ExplainPolicy = bool | Callable[[PredictionResult, RiskScore], bool]


def run_ids(served_ensemble: ServedEnsemble) -> tuple[str, str, str | None]:
    classifier = served_ensemble.classifier
    label_column = classifier.metadata.get("label_column", "is_attack")
    anomaly_run_id = (
        served_ensemble.anomaly_detector.run_id
        if served_ensemble.anomaly_detector is not None
        else None
    )
    return classifier.run_id, label_column, anomaly_run_id


def row_to_json_safe_dict(row: pd.Series) -> dict[str, Any]:
    """pandas/numpy scalar values (from a CSV/PCAP-derived row) aren't
    JSON-serializable as-is -- same `.item()`-if-present pattern
    `nids.api.inference._to_builtin` already uses for prediction values."""
    return {key: (value.item() if hasattr(value, "item") else value) for key, value in row.items()}


def _to_explanation_response(explanation: Explanation) -> ExplanationResponse:
    return ExplanationResponse(
        base_value=explanation.base_value,
        top_features=[
            FeatureContributionResponse(
                feature=f.feature, value=f.value, contribution=f.contribution, direction=f.direction
            )
            for f in explanation.top_features
        ],
        summary=explanation.summary,
    )


def _to_risk_response(risk_score: RiskScore) -> RiskScoreResponse:
    return RiskScoreResponse(
        score=risk_score.score, severity=risk_score.severity, factors=risk_score.factors
    )


def _to_mitre_response(mitre: MitreMapping) -> MitreMappingResponse:
    return MitreMappingResponse(
        tactic=mitre.tactic,
        techniques=[
            MitreTechniqueResponse(id=t.id, name=t.name, url=t.url) for t in mitre.techniques
        ],
    )


def to_response(
    result: PredictionResult,
    risk_score: RiskScore,
    mitre: MitreMapping | None,
    alert_id: str | None,
    explanation: Explanation | None = None,
) -> PredictResponse:
    return PredictResponse(
        prediction=result.prediction,
        probabilities=result.probabilities,
        confidence=result.confidence,
        attack_category=result.attack_category,
        anomaly_score=result.anomaly_score,
        is_anomaly=result.is_anomaly,
        severity=result.severity,
        explanation=_to_explanation_response(explanation) if explanation is not None else None,
        risk_score=_to_risk_response(risk_score),
        mitre=_to_mitre_response(mitre) if mitre is not None else None,
        alert_id=alert_id,
    )


def persist_if_configured(
    db_engine: Engine | None,
    result: PredictionResult,
    risk_score: RiskScore,
    mitre: MitreMapping | None,
    raw_record: dict[str, Any],
    run_id: str,
    label_column: str,
    anomaly_run_id: str | None,
    explanation: Explanation | None,
    alert: Alert | None,
    source: str = "api",
    device_id: str | None = None,
) -> None:
    """Writes are entirely opt-in (`db_engine is None` when no
    `database_url` was configured) -- alert *generation* already happened
    unconditionally by the time this is called; this only decides whether
    to record it. `device_id` is `None` for HTTP-originated predictions
    and set for live-agent-originated ones (see `nids.api.worker`)."""
    if db_engine is None:
        return
    prediction_id = save_prediction(
        db_engine,
        result,
        risk_score,
        mitre,
        raw_record,
        run_id,
        label_column,
        anomaly_run_id=anomaly_run_id,
        explanation=explanation,
        source=source,
        device_id=device_id,
    )
    if alert is not None:
        save_alert(db_engine, prediction_id, alert, device_id=device_id)


def finish_record(
    served_ensemble: ServedEnsemble,
    result: PredictionResult,
    record: dict[str, Any],
    explanation: Explanation | None,
    *,
    config: ServingConfig,
    db_engine: Engine | None,
    persist: bool = True,
    source: str = "api",
    device_id: str | None = None,
    notify: Callable[[Alert], None] | None = None,
) -> PredictResponse:
    """risk -> mitre -> alert -> optional persist -> response, given an
    already-computed prediction (and, optionally, explanation).

    `notify`, if given, is called with the `Alert` when one is generated
    *and* its severity meets `config.notification_min_severity` -- the
    caller (`nids.api.app`/`nids.api.worker`) decides what "notify"
    means (see `nids.api.notifications.publish.schedule_alert_publish`);
    this module stays free of any bus/asyncio import, matching its own
    "pure orchestration" docstring."""
    risk_score = compute_risk_score(result)
    mitre = map_to_mitre(result.attack_category)
    alert = generate_alert(
        result, risk_score, mitre, explanation, threshold=config.alert_threshold, source=source
    )
    if alert is not None and notify is not None and meets_min_severity(
        alert.level, config.notification_min_severity
    ):
        notify(alert)

    if persist:
        run_id, label_column, anomaly_run_id = run_ids(served_ensemble)
        persist_if_configured(
            db_engine,
            result,
            risk_score,
            mitre,
            record,
            run_id,
            label_column,
            anomaly_run_id,
            explanation,
            alert,
            source=source,
            device_id=device_id,
        )

    alert_id = alert.alert_id if alert is not None else None
    return to_response(result, risk_score, mitre, alert_id, explanation)


def process_record(
    served_ensemble: ServedEnsemble,
    record: dict[str, Any],
    *,
    config: ServingConfig,
    db_engine: Engine | None,
    explain: ExplainPolicy = False,
    persist: bool = True,
    source: str = "api",
    device_id: str | None = None,
    notify: Callable[[Alert], None] | None = None,
) -> PredictResponse:
    """Run one raw record through the full pipeline: predict -> optional
    explain -> risk -> mitre -> alert -> optional persist -> response.
    The single-record entry point -- the HTTP `/predict` route and the
    live worker both call this, not two copies of this orchestration.
    """
    result = predict_one(served_ensemble, record)
    risk_score_for_policy = compute_risk_score(result) if callable(explain) else None
    should_explain = (
        explain(result, risk_score_for_policy) if callable(explain) else explain
    )
    explanation = explain_one(served_ensemble, record, result.prediction) if should_explain else None

    return finish_record(
        served_ensemble,
        result,
        record,
        explanation,
        config=config,
        db_engine=db_engine,
        persist=persist,
        source=source,
        device_id=device_id,
        notify=notify,
    )
