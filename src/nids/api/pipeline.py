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

from nids.api.alerts import Alert, generate_alert, meets_min_severity, severity_rank
from nids.api.config import ServingConfig
from nids.api.explain import Explanation, explain_one
from nids.api.inference import PredictionResult, predict_one
from nids.api.metrics import Metrics
from nids.api.mitre import MitreMapping, map_to_mitre
from nids.api.model_loader import ServedEnsemble
from nids.api.risk import RiskScore, compute_risk_score
from nids.api.rules import evaluate_rules, generate_rule_alert
from nids.api.schemas import (
    ExplanationResponse,
    FeatureContributionResponse,
    MitreMappingResponse,
    MitreTechniqueResponse,
    PredictResponse,
    RiskScoreResponse,
)
from nids.api.store import save_alert, save_prediction
from nids.api.threat_intel import extract_indicators

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
    alerts: list[Alert],
    source: str = "api",
    device_id: str | None = None,
) -> None:
    """Writes are entirely opt-in (`db_engine is None` when no
    `database_url` was configured) -- alert *generation* already happened
    unconditionally by the time this is called; this only decides whether
    to record it. `device_id` is `None` for HTTP-originated predictions
    and set for live-agent-originated ones (see `nids.api.worker`).

    `alerts` may hold more than one entry -- the ML classifier
    (`generate_alert`) and a signature match (`nids.api.rules.
    evaluate_rules`) can both fire independently for the same record.
    `AlertRecord.prediction_id` is a one-to-many relationship (see
    `nids.api.store.PredictionRecord.alerts`) precisely so this is safe:
    each alert here becomes its own row against the one `prediction_id`
    this call creates."""
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
        # str(...)-wrapped: raw_record is `dict[str, Any]`, and these two
        # keys only ever exist when nids.flows.aggregator.FlowAggregator
        # put them there (see its docstring) -- never for source="api",
        # since NSL-KDD has no IP field at all to have supplied one.
        src_ip=str(raw_record["src_ip"]) if raw_record.get("src_ip") else None,
        dst_ip=str(raw_record["dst_ip"]) if raw_record.get("dst_ip") else None,
    )
    for alert in alerts:
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
    enrich: Callable[[list[str]], None] | None = None,
    metrics: Metrics | None = None,
) -> PredictResponse:
    """risk -> mitre -> alert -> optional persist -> response, given an
    already-computed prediction (and, optionally, explanation).

    `notify`, if given, is called once per `Alert` generated (there may
    be zero, one, or two: the ML classifier via `generate_alert` and a
    signature match via `nids.api.rules.evaluate_rules` fire
    independently) whose severity meets
    `config.notification_min_severity` -- the caller (`nids.api.app`/
    `nids.api.worker`) decides what "notify" means (see
    `nids.api.notifications.publish.schedule_alert_publish`); this
    module stays free of any bus/asyncio import, matching its own "pure
    orchestration" docstring.

    `enrich`, if given, is called at most once, with the record's
    routable IPv4 indicators (`nids.api.threat_intel.extract_indicators`
    -- empty for `source="api"`, since NSL-KDD has no IP field at all;
    see `nids.api.threat_intel`'s module docstring), but *only* when at
    least one alert actually fired. Threat-intel enrichment is
    investigative context for something already flagged, not a check run
    against every flow -- the same "not every prediction, only the
    alert-worthy ones" gating `nids.api.worker.explain_only_alert_worthy`
    already applies for SHAP, applied here to conserve external provider
    rate limits instead of compute. Never influences `alerts` above --
    called after they're already decided, same ordering guarantee
    `notify` gets.

    `metrics`, if given, gets `alerts_raised_total` incremented once per
    `Alert` actually generated, labeled with that alert's own `.source`
    -- not a caller-supplied transport label. This lives here (not at
    the `nids.api.app`/`nids.api.worker` call sites, as it did before
    rule-based detection existed) because only this function knows how
    many alerts actually fired and what each one's real source is;
    `PredictResponse.alert_id` names only the primary one, so a caller
    working from the response alone would under-count whenever both an
    ML and a rule alert fire for the same record.

    Rule evaluation runs against `record` (the raw feature dict) only --
    never against `result` -- so a rule can fire on a record the
    classifier doesn't flag at all, and vice versa; the two paths never
    influence each other. When both fire, `alert_id` on the returned
    response is whichever is higher severity (`nids.api.alerts.
    severity_rank`; a tie prefers the rule match, since it's a
    deterministic signature hit rather than a probabilistic one) -- but
    *both* are still persisted/notified/counted independently; only the
    single HTTP response field (`PredictResponse.alert_id`, unchanged
    shape for frontend compatibility) can name just one.
    """
    risk_score = compute_risk_score(result)
    mitre = map_to_mitre(result.attack_category)
    ml_alert = generate_alert(
        result, risk_score, mitre, explanation, threshold=config.alert_threshold, source=source
    )
    matched_rule = evaluate_rules(record)
    rule_alert = generate_rule_alert(matched_rule) if matched_rule is not None else None
    # rule_alert first: on an exact severity tie, max()'s left-to-right
    # stability (see the docstring above) picks it as the primary alert.
    alerts = [a for a in (rule_alert, ml_alert) if a is not None]

    if notify is not None:
        for alert in alerts:
            if meets_min_severity(alert.level, config.notification_min_severity):
                notify(alert)

    if enrich is not None and alerts:
        indicators = extract_indicators(record)
        if indicators:
            enrich(indicators)

    if metrics is not None:
        for alert in alerts:
            metrics.alerts_raised_total.labels(source=alert.source).inc()

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
            alerts,
            source=source,
            device_id=device_id,
        )

    primary_alert = max(alerts, key=lambda a: severity_rank(a.level)) if alerts else None
    alert_id = primary_alert.alert_id if primary_alert is not None else None
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
    enrich: Callable[[list[str]], None] | None = None,
    metrics: Metrics | None = None,
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
        enrich=enrich,
        metrics=metrics,
    )
