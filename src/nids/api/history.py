"""History API: read access to persisted predictions and alerts (see
`nids.api.store`), plus the one write action a SOC workflow needs --
acknowledging an alert.

A second `APIRouter`, included in `create_app` alongside the predict
router exactly the way `docs/API.md` has documented as the extension
pattern since Milestone 2 -- this module changes nothing about
`api/app.py`'s existing routes.

Every route here 503s if no database is configured, the same "state
doesn't exist" pattern `api/app.py`'s `_get_served_ensemble` already uses
for an unloaded model.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.engine import Engine

from nids.api.schemas import (
    AlertHistoryItem,
    AlertHistoryResponse,
    PredictionHistoryItem,
    PredictionHistoryResponse,
)
from nids.api.store import (
    AlertRecordView,
    PredictionRecordView,
    acknowledge_alert,
    get_alert,
    get_prediction,
    list_alerts,
    list_predictions,
)

router = APIRouter(prefix="/history")

_MAX_LIMIT = 100
_LimitQuery = Query(20, ge=1, le=_MAX_LIMIT, description="Page size.")
_OffsetQuery = Query(0, ge=0, description="Number of items to skip.")


def _get_db_engine(request: Request) -> Engine:
    db_engine = getattr(request.app.state, "db_engine", None)
    if db_engine is None:
        raise HTTPException(
            status_code=503, detail="No database is configured for this deployment."
        )
    return db_engine


DbEngineDep = Annotated[Engine, Depends(_get_db_engine)]


def _to_prediction_item(view: PredictionRecordView) -> PredictionHistoryItem:
    return PredictionHistoryItem(
        id=view.id,
        created_at=view.created_at,
        run_id=view.run_id,
        anomaly_run_id=view.anomaly_run_id,
        label_column=view.label_column,
        prediction=view.prediction,
        probabilities=view.probabilities,
        confidence=view.confidence,
        attack_category=view.attack_category,
        anomaly_score=view.anomaly_score,
        is_anomaly=view.is_anomaly,
        severity=view.severity,
        risk_score=view.risk_score,
        risk_factors=view.risk_factors,
        mitre=view.mitre,
        raw_record=view.raw_record,
        source=view.source,
        explanation=(
            {
                "base_value": view.explanation.base_value,
                "top_features": view.explanation.top_features,
                "summary": view.explanation.summary,
            }
            if view.explanation is not None
            else None
        ),
    )


def _to_alert_item(view: AlertRecordView) -> AlertHistoryItem:
    return AlertHistoryItem(
        id=view.id,
        prediction_id=view.prediction_id,
        created_at=view.created_at,
        level=view.level,
        title=view.title,
        message=view.message,
        risk_score=view.risk_score,
        attack_category=view.attack_category,
        mitre=view.mitre,
        acknowledged=view.acknowledged,
        source=view.source,
    )


@router.get("/predictions", response_model=PredictionHistoryResponse)
def list_predictions_route(
    db_engine: DbEngineDep,
    severity: str | None = None,
    attack_category: str | None = None,
    min_risk_score: float | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = _LimitQuery,
    offset: int = _OffsetQuery,
) -> PredictionHistoryResponse:
    page = list_predictions(
        db_engine,
        severity=severity,
        attack_category=attack_category,
        min_risk_score=min_risk_score,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    return PredictionHistoryResponse(
        items=[_to_prediction_item(i) for i in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/predictions/{prediction_id}", response_model=PredictionHistoryItem)
def get_prediction_route(prediction_id: str, db_engine: DbEngineDep) -> PredictionHistoryItem:
    view = get_prediction(db_engine, prediction_id)
    if view is None:
        raise HTTPException(status_code=404, detail=f"No prediction found with id {prediction_id!r}.")
    return _to_prediction_item(view)


@router.get("/alerts", response_model=AlertHistoryResponse)
def list_alerts_route(
    db_engine: DbEngineDep,
    level: str | None = None,
    acknowledged: bool | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = _LimitQuery,
    offset: int = _OffsetQuery,
) -> AlertHistoryResponse:
    page = list_alerts(
        db_engine,
        level=level,
        acknowledged=acknowledged,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    return AlertHistoryResponse(
        items=[_to_alert_item(i) for i in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/alerts/{alert_id}", response_model=AlertHistoryItem)
def get_alert_route(alert_id: str, db_engine: DbEngineDep) -> AlertHistoryItem:
    view = get_alert(db_engine, alert_id)
    if view is None:
        raise HTTPException(status_code=404, detail=f"No alert found with id {alert_id!r}.")
    return _to_alert_item(view)


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertHistoryItem)
def acknowledge_alert_route(alert_id: str, db_engine: DbEngineDep) -> AlertHistoryItem:
    view = acknowledge_alert(db_engine, alert_id)
    if view is None:
        raise HTTPException(status_code=404, detail=f"No alert found with id {alert_id!r}.")
    return _to_alert_item(view)
