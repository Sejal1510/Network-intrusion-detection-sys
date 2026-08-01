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
from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Request, UploadFile
from pandas.errors import EmptyDataError, ParserError

from nids.api.config import ServingConfig
from nids.api.inference import PredictionResult, predict_batch, predict_one
from nids.api.model_loader import ServedEnsemble, load_served_ensemble
from nids.api.schemas import (
    BatchPredictResponse,
    BatchPredictSummary,
    HealthResponse,
    ModelInfoResponse,
    PredictRequest,
    PredictResponse,
)

router = APIRouter()


def _get_served_ensemble(request: Request) -> ServedEnsemble:
    served_ensemble = getattr(request.app.state, "served_ensemble", None)
    if served_ensemble is None:
        raise HTTPException(status_code=503, detail="No model is loaded.")
    return served_ensemble


ServedEnsembleDep = Annotated[ServedEnsemble, Depends(_get_served_ensemble)]


def _to_response(result: PredictionResult) -> PredictResponse:
    return PredictResponse(prediction=result.prediction, probabilities=result.probabilities)


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    served_ensemble = getattr(request.app.state, "served_ensemble", None)
    return HealthResponse(status="ok", model_loaded=served_ensemble is not None)


@router.get("/model", response_model=ModelInfoResponse)
def model_info(served_ensemble: ServedEnsembleDep) -> ModelInfoResponse:
    classifier = served_ensemble.classifier
    return ModelInfoResponse(
        run_id=classifier.run_id,
        model_name=classifier.metadata.get("model_name", "unknown"),
        label_column=classifier.metadata.get("label_column"),
        metrics=classifier.metrics,
        metadata=classifier.metadata,
    )


@router.post("/predict", response_model=PredictResponse)
def predict(payload: PredictRequest, served_ensemble: ServedEnsembleDep) -> PredictResponse:
    try:
        result = predict_one(served_ensemble, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_response(result)


@router.post("/predict/batch", response_model=BatchPredictResponse)
async def predict_batch_csv(
    served_ensemble: ServedEnsembleDep, file: Annotated[UploadFile, File(...)]
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

    prediction_counts: dict[str, int] = {}
    for result in results:
        key = str(result.prediction)
        prediction_counts[key] = prediction_counts.get(key, 0) + 1

    return BatchPredictResponse(
        summary=BatchPredictSummary(total_records=len(results), prediction_counts=prediction_counts),
        results=[_to_response(r) for r in results],
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
