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
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from pandas.errors import EmptyDataError, ParserError

from nids.api.config import ServingConfig
from nids.api.explain import Explanation, explain_batch, explain_one
from nids.api.inference import PredictionResult, predict_batch, predict_one
from nids.api.model_loader import ServedEnsemble, load_served_ensemble
from nids.api.schemas import (
    BatchPredictResponse,
    BatchPredictSummary,
    ExplanationResponse,
    FeatureContributionResponse,
    HealthResponse,
    ModelInfoResponse,
    PredictRequest,
    PredictResponse,
    ServedRunInfo,
)

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


def _to_response(
    result: PredictionResult, explanation: Explanation | None = None
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
    )


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


@router.post("/predict", response_model=PredictResponse)
def predict(
    payload: PredictRequest,
    served_ensemble: ServedEnsembleDep,
    explain: bool = _EXPLAIN_QUERY,
) -> PredictResponse:
    record = payload.model_dump()
    try:
        result = predict_one(served_ensemble, record)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    explanation = explain_one(served_ensemble, record, result.prediction) if explain else None
    return _to_response(result, explanation)


@router.post("/predict/batch", response_model=BatchPredictResponse)
async def predict_batch_csv(
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

    prediction_counts: dict[str, int] = {}
    for result in results:
        key = str(result.prediction)
        prediction_counts[key] = prediction_counts.get(key, 0) + 1

    return BatchPredictResponse(
        summary=BatchPredictSummary(total_records=len(results), prediction_counts=prediction_counts),
        results=[
            _to_response(r, e) for r, e in zip(results, explanations, strict=True)
        ],
    )


def create_app(config: ServingConfig) -> FastAPI:
    """Build a fully wired app serving the run(s) pinned by `config`.

    Loading happens here rather than lazily on first request, so a bad
    run_id or corrupt run directory fails at startup.
    """
    app = FastAPI(title="NIDS Inference API")
    app.state.served_ensemble = load_served_ensemble(config)
    app.include_router(router)
    return app
