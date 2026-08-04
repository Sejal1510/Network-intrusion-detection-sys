"""FastAPI application: the HTTP boundary for nids.api.inference.

Routes only parse/validate requests, delegate to `nids.api.pipeline` for
all per-record orchestration (predict, explain, risk, mitre, alert,
persist), and format responses -- no ML logic lives here. The app loads
its pinned model once at creation time (see `nids.api.model_loader`) and
stores it on `app.state`, so a bad run_id or a corrupt run directory is a
startup-time failure, not a per-request one.

Structured as one `APIRouter` now so future endpoint groups (capture,
agent ingestion -- see docs/API.md) can be added as their own `APIRouter`
modules and included alongside this one without touching it.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import secrets
from collections.abc import AsyncIterator
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pandas.errors import EmptyDataError, ParserError

from nids.api.broadcast import router as broadcast_router
from nids.api.bus import InMemoryBus, create_bus
from nids.api.config import ServingConfig
from nids.api.explain import Explanation, explain_batch
from nids.api.history import router as history_router
from nids.api.inference import predict_batch
from nids.api.ingest import router as ingest_router
from nids.api.mitre import list_all_mappings
from nids.api.model_loader import ServedEnsemble, load_served_ensemble
from nids.api.pipeline import finish_record, process_record, row_to_json_safe_dict
from nids.api.schemas import (
    BatchPredictResponse,
    BatchPredictSummary,
    HealthResponse,
    MitreMappingResponse,
    MitreTechniqueResponse,
    ModelInfoResponse,
    PredictRequest,
    PredictResponse,
    ServedRunInfo,
)
from nids.api.store import create_db_engine
from nids.api.worker import run_worker

router = APIRouter()


def _get_served_ensemble(request: Request) -> ServedEnsemble:
    served_ensemble = getattr(request.app.state, "served_ensemble", None)
    if served_ensemble is None:
        raise HTTPException(status_code=503, detail="No model is loaded.")
    return served_ensemble


ServedEnsembleDep = Annotated[ServedEnsemble, Depends(_get_served_ensemble)]


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    served_ensemble = getattr(request.app.state, "served_ensemble", None)
    return HealthResponse(
        status="ok",
        model_loaded=served_ensemble is not None,
        database_configured=getattr(request.app.state, "db_engine", None) is not None,
    )


@router.get("/mitre", response_model=dict[str, MitreMappingResponse])
def mitre_mappings() -> dict[str, MitreMappingResponse]:
    """The full ATT&CK category -> tactic/technique table (see
    nids.api.mitre), so a dashboard can render a reference panel without
    bundling its own copy of mitre_attack_mapping.json."""
    return {
        category: MitreMappingResponse(
            tactic=mapping.tactic,
            techniques=[
                MitreTechniqueResponse(id=t.id, name=t.name, url=t.url)
                for t in mapping.techniques
            ],
        )
        for category, mapping in list_all_mappings().items()
    }


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
    request: Request,
    served_ensemble: ServedEnsembleDep,
    explain: bool = _EXPLAIN_QUERY,
) -> PredictResponse:
    record = payload.model_dump()
    config: ServingConfig = request.app.state.serving_config
    try:
        return process_record(
            served_ensemble,
            record,
            config=config,
            db_engine=request.app.state.db_engine,
            explain=explain,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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

    prediction_counts: dict[str, int] = {}
    responses: list[PredictResponse] = []
    for row_idx, (result, explanation) in enumerate(zip(results, explanations, strict=True)):
        key = str(result.prediction)
        prediction_counts[key] = prediction_counts.get(key, 0) + 1

        # finish_record, not process_record: predict_batch/explain_batch
        # already ran vectorized above -- calling process_record per row
        # would re-predict/re-explain one row at a time and silently lose
        # that vectorization.
        responses.append(
            finish_record(
                served_ensemble,
                result,
                row_to_json_safe_dict(df.iloc[row_idx]),
                explanation,
                config=config,
                db_engine=db_engine,
            )
        )

    return BatchPredictResponse(
        summary=BatchPredictSummary(total_records=len(results), prediction_counts=prediction_counts),
        results=responses,
    )


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Starts the live worker (`nids.api.worker.run_worker`) as a
    background task for the `InMemoryBus` tier only -- with `RedisBus`,
    the worker is meant to run as its own process
    (`python -m nids.api.worker`), scaling independently via Redis
    Streams consumer groups; auto-starting a second in-process consumer
    there would just be a redundant, harder-to-reason-about competing
    consumer in the same group.
    """
    worker_task: asyncio.Task | None = None
    if isinstance(app.state.bus, InMemoryBus):
        worker_task = asyncio.create_task(
            run_worker(
                app.state.bus, app.state.served_ensemble, app.state.serving_config, app.state.db_engine
            )
        )
    try:
        yield
    finally:
        if worker_task is not None:
            worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker_task


def create_app(config: ServingConfig) -> FastAPI:
    """Build a fully wired app serving the run(s) pinned by `config`.

    Loading happens here rather than lazily on first request, so a bad
    run_id or corrupt run directory fails at startup. `db_engine` is
    `None` unless `config.database_url` is set -- persistence is entirely
    opt-in (see `nids.api.store`). `bus` is an `InMemoryBus` unless
    `config.redis_url` is set (see `nids.api.bus`) -- live monitoring
    works out of the box with zero new infrastructure either way.
    `secret_key` (for agent pairing tokens, see `nids.api.agent_auth`) is
    generated once at startup if not set explicitly.
    """
    app = FastAPI(title="NIDS Inference API", lifespan=_lifespan)
    if config.cors_origins:
        # allow_credentials stays off: the dashboard authenticates via a
        # ?token= query param (see nids.api.broadcast), never cookies, so
        # there's no session state that needs credentialed CORS.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(config.cors_origins),
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.state.served_ensemble = load_served_ensemble(config)
    app.state.serving_config = config
    app.state.db_engine = create_db_engine(config.database_url) if config.database_url else None
    app.state.bus = create_bus(config.redis_url)
    app.state.secret_key = config.secret_key or secrets.token_urlsafe(32)
    app.include_router(router)
    app.include_router(history_router)
    app.include_router(ingest_router)
    app.include_router(broadcast_router)
    return app
