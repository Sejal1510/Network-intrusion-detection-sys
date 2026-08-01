"""FastAPI application: the HTTP boundary for nids.api.inference.

Routes only parse/validate requests, delegate to `nids.api.inference` for
all prediction logic, and format responses -- no ML logic lives here. The
app loads its pinned model once at creation time (see
`nids.api.model_loader`) and stores it on `app.state`, so a bad run_id or a
corrupt run directory is a startup-time failure, not a per-request one.

Structured as one `APIRouter` now so future endpoint groups (explain,
capture, history, alerts -- see docs/API.md) can be added as their own
`APIRouter` modules and included alongside this one without touching it.
"""

from __future__ import annotations

import io
from typing import Annotated, Any

import pandas as pd
from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from pandas.errors import EmptyDataError, ParserError
from sqlalchemy.engine import Engine

from nids.api.alerts import Alert, generate_alert
from nids.api.config import ServingConfig
from nids.api.explain import Explanation, explain_batch, explain_one
from nids.api.inference import PredictionResult, predict_batch, predict_one
from nids.api.mitre import MitreMapping, map_to_mitre
from nids.api.model_loader import ServedEnsemble, load_served_ensemble
from nids.api.risk import RiskScore, compute_risk_score
from nids.api.schemas import (
    BatchPredictResponse,
    BatchPredictSummary,
    ExplanationResponse,
    FeatureContributionResponse,
    HealthResponse,
    MitreMappingResponse,
    MitreTechniqueResponse,
    ModelInfoResponse,
    PredictRequest,
    PredictResponse,
    RiskScoreResponse,
    ServedRunInfo,
)
from nids.api.store import create_db_engine, save_alert, save_prediction

router = APIRouter()


def _get_served_ensemble(request: Request) -> ServedEnsemble:
    served_ensemble = getattr(request.app.state, "served_ensemble", None)
    if served_ensemble is None:
        raise HTTPException(status_code=503, detail="No model is loaded.")
    return served_ensemble


ServedEnsembleDep = Annotated[ServedEnsemble, Depends(_get_served_ensemble)]


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
    return RiskScoreResponse(score=risk_score.score, severity=risk_score.severity, factors=risk_score.factors)


def _to_mitre_response(mitre: MitreMapping) -> MitreMappingResponse:
    return MitreMappingResponse(
        tactic=mitre.tactic,
        techniques=[
            MitreTechniqueResponse(id=t.id, name=t.name, url=t.url) for t in mitre.techniques
        ],
    )


def _to_response(
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


def _row_to_json_safe_dict(row: pd.Series) -> dict[str, Any]:
    """pandas/numpy scalar values (from a CSV-derived row) aren't JSON-
    serializable as-is -- same `.item()`-if-present pattern
    `nids.api.inference._to_builtin` already uses for prediction values,
    applied here to every value in a raw input record before persisting
    it (see `nids.api.store`)."""
    return {key: (value.item() if hasattr(value, "item") else value) for key, value in row.items()}


def _persist_if_configured(
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
) -> None:
    """Writes are entirely opt-in (`db_engine is None` when no
    `database_url` was configured) -- alert *generation* already happened
    unconditionally by the time this is called; this only decides whether
    to record it."""
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
    )
    if alert is not None:
        save_alert(db_engine, prediction_id, alert)


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    served_ensemble = getattr(request.app.state, "served_ensemble", None)
    return HealthResponse(status="ok", model_loaded=served_ensemble is not None)


@router.get("/model", response_model=ModelInfoResponse)
def model_info(served_ensemble: ServedEnsembleDep) -> ModelInfoResponse:
    classifier = served_ensemble.classifier
    anomaly_detector = served_ensemble.anomaly_detector
    return ModelInfoResponse(
        run_id=classifier.run_id,
        model_name=classifier.metadata.get("model_name", "unknown"),
        label_column=classifier.metadata.get("label_column"),
        metrics=classifier.metrics,
        metadata=classifier.metadata,
        anomaly_detector=(
            ServedRunInfo(
                run_id=anomaly_detector.run_id,
                model_name=anomaly_detector.metadata.get("model_name", "unknown"),
                metrics=anomaly_detector.metrics,
                metadata=anomaly_detector.metadata,
            )
            if anomaly_detector is not None
            else None
        ),
    )


_EXPLAIN_QUERY = Query(False, description="Include a SHAP-based explanation of the classifier's prediction.")


def _run_ids(served_ensemble: ServedEnsemble) -> tuple[str, str, str | None]:
    classifier = served_ensemble.classifier
    label_column = classifier.metadata.get("label_column", "is_attack")
    anomaly_run_id = (
        served_ensemble.anomaly_detector.run_id
        if served_ensemble.anomaly_detector is not None
        else None
    )
    return classifier.run_id, label_column, anomaly_run_id


@router.post("/predict", response_model=PredictResponse)
def predict(
    payload: PredictRequest,
    request: Request,
    served_ensemble: ServedEnsembleDep,
    explain: bool = _EXPLAIN_QUERY,
) -> PredictResponse:
    record = payload.model_dump()
    try:
        result = predict_one(served_ensemble, record)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    explanation = explain_one(served_ensemble, record, result.prediction) if explain else None
    risk_score = compute_risk_score(result)
    mitre = map_to_mitre(result.attack_category)

    config: ServingConfig = request.app.state.serving_config
    alert = generate_alert(result, risk_score, mitre, explanation, threshold=config.alert_threshold)

    run_id, label_column, anomaly_run_id = _run_ids(served_ensemble)
    _persist_if_configured(
        request.app.state.db_engine,
        result,
        risk_score,
        mitre,
        record,
        run_id,
        label_column,
        anomaly_run_id,
        explanation,
        alert,
    )

    alert_id = alert.alert_id if alert is not None else None
    return _to_response(result, risk_score, mitre, alert_id, explanation)


@router.post("/predict/batch", response_model=BatchPredictResponse)
async def predict_batch_csv(
    request: Request,
    served_ensemble: ServedEnsembleDep,
    file: Annotated[UploadFile, File(...)],
    explain: bool = _EXPLAIN_QUERY,
) -> BatchPredictResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a .csv file.")

    raw_bytes = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw_bytes))
    except (ParserError, EmptyDataError, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {exc}") from exc

    try:
        results = predict_batch(served_ensemble, df)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if explain:
        explanations: list[Explanation | None] = list(
            explain_batch(served_ensemble, df, [r.prediction for r in results])
        )
    else:
        explanations = [None] * len(results)

    config: ServingConfig = request.app.state.serving_config
    db_engine = request.app.state.db_engine
    run_id, label_column, anomaly_run_id = _run_ids(served_ensemble)

    prediction_counts: dict[str, int] = {}
    responses: list[PredictResponse] = []
    for row_idx, (result, explanation) in enumerate(zip(results, explanations, strict=True)):
        key = str(result.prediction)
        prediction_counts[key] = prediction_counts.get(key, 0) + 1

        risk_score = compute_risk_score(result)
        mitre = map_to_mitre(result.attack_category)
        alert = generate_alert(result, risk_score, mitre, explanation, threshold=config.alert_threshold)

        _persist_if_configured(
            db_engine,
            result,
            risk_score,
            mitre,
            _row_to_json_safe_dict(df.iloc[row_idx]),
            run_id,
            label_column,
            anomaly_run_id,
            explanation,
            alert,
        )

        alert_id = alert.alert_id if alert is not None else None
        responses.append(_to_response(result, risk_score, mitre, alert_id, explanation))

    return BatchPredictResponse(
        summary=BatchPredictSummary(total_records=len(results), prediction_counts=prediction_counts),
        results=responses,
    )


def create_app(config: ServingConfig) -> FastAPI:
    """Build a fully wired app serving the run(s) pinned by `config`.

    Loading happens here rather than lazily on first request, so a bad
    run_id or corrupt run directory fails at startup. `db_engine` is
    `None` unless `config.database_url` is set -- persistence is entirely
    opt-in (see `nids.api.store`).
    """
    app = FastAPI(title="NIDS Inference API")
    app.state.served_ensemble = load_served_ensemble(config)
    app.state.serving_config = config
    app.state.db_engine = create_db_engine(config.database_url) if config.database_url else None
    app.include_router(router)
    return app
