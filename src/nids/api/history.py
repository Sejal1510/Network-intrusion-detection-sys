"""History API: read access to persisted predictions and alerts (see
`nids.api.store`), plus the one write action a SOC workflow needs --
acknowledging an alert.

A second `APIRouter`, included in `create_app` alongside the predict
router exactly the way `docs/API.md` has documented as the extension
pattern since Milestone 2 -- this module changes nothing about
`api/app.py`'s existing routes.

Every route here 503s if no database is configured, the same "state
doesn't exist" pattern `api/app.py`'s `_get_served_ensemble` already uses
for an unloaded model. Every route also requires a logged-in session
(`nids.api.auth.CurrentUserDep`, Milestone 11) -- 401s without one.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.engine import Engine

from nids.api.auth import CurrentUserDep
from nids.api.schemas import (
    AlertHistoryItem,
    AlertHistoryResponse,
    AuditEventItem,
    AuditEventResponse,
    EnrichmentListResponse,
    EnrichmentResultResponse,
    PredictionHistoryItem,
    PredictionHistoryResponse,
)
from nids.api.store import (
    AlertRecordView,
    AuditEventView,
    IocEnrichmentView,
    PredictionRecordView,
    acknowledge_alert,
    get_alert,
    get_prediction,
    list_alerts,
    list_audit_events,
    list_enrichments_for_indicators,
    list_predictions,
    record_audit_event,
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


def _enrichment_items_for(
    view: PredictionRecordView, cached: list[IocEnrichmentView]
) -> list[EnrichmentResultResponse]:
    """One response row per (cached result, matching role) pair -- `view`
    tells us which of `src_ip`/`dst_ip` this specific prediction actually
    had; `cached` (from `nids.api.store.list_enrichments_for_indicators`)
    is indicator-only and role-agnostic (see that function's docstring),
    since the same IP's cached verdict is shared across every prediction
    that ever referenced it. An indicator matching both roles (e.g. a
    reflected/looped flow) gets one row per role, not silently merged."""
    roles_by_indicator: dict[str, list[str]] = {}
    if view.src_ip:
        roles_by_indicator.setdefault(view.src_ip, []).append("src")
    if view.dst_ip:
        roles_by_indicator.setdefault(view.dst_ip, []).append("dst")

    items: list[EnrichmentResultResponse] = []
    for result in cached:
        for role in roles_by_indicator.get(result.indicator, []):
            items.append(
                EnrichmentResultResponse(
                    indicator=result.indicator,
                    indicator_role=role,
                    provider=result.provider,
                    verdict=result.verdict,
                    confidence=result.confidence,
                    raw_response=result.raw_response,
                    looked_up_at=result.looked_up_at,
                    expires_at=result.expires_at,
                )
            )
    return items


def _to_audit_event_item(view: AuditEventView) -> AuditEventItem:
    return AuditEventItem(
        id=view.id,
        created_at=view.created_at,
        event_type=view.event_type,
        actor=view.actor,
        target_id=view.target_id,
        detail=view.detail,
    )


@router.get("/predictions", response_model=PredictionHistoryResponse)
def list_predictions_route(
    db_engine: DbEngineDep,
    _current_user: CurrentUserDep,
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
def get_prediction_route(
    prediction_id: str, db_engine: DbEngineDep, _current_user: CurrentUserDep
) -> PredictionHistoryItem:
    view = get_prediction(db_engine, prediction_id)
    if view is None:
        raise HTTPException(status_code=404, detail=f"No prediction found with id {prediction_id!r}.")
    return _to_prediction_item(view)


@router.get("/alerts", response_model=AlertHistoryResponse)
def list_alerts_route(
    db_engine: DbEngineDep,
    _current_user: CurrentUserDep,
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
def get_alert_route(
    alert_id: str, db_engine: DbEngineDep, _current_user: CurrentUserDep
) -> AlertHistoryItem:
    view = get_alert(db_engine, alert_id)
    if view is None:
        raise HTTPException(status_code=404, detail=f"No alert found with id {alert_id!r}.")
    return _to_alert_item(view)


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertHistoryItem)
def acknowledge_alert_route(
    alert_id: str, db_engine: DbEngineDep, current_user: CurrentUserDep
) -> AlertHistoryItem:
    view = acknowledge_alert(db_engine, alert_id)
    if view is None:
        raise HTTPException(status_code=404, detail=f"No alert found with id {alert_id!r}.")
    record_audit_event(
        db_engine,
        event_type="alert_acknowledged",
        actor=f"user:{current_user.username}",
        target_id=alert_id,
    )
    return _to_alert_item(view)


@router.get("/predictions/{prediction_id}/enrichment", response_model=EnrichmentListResponse)
def get_prediction_enrichment_route(
    prediction_id: str, db_engine: DbEngineDep, _current_user: CurrentUserDep
) -> EnrichmentListResponse:
    """Whatever threat-intel is currently cached for this prediction's
    `src_ip`/`dst_ip` (nids.api.threat_intel) -- an empty list is a valid,
    normal response, not an error: it means either this prediction has no
    routable IPv4 indicators at all (always true for source="api", see
    `nids.api.store.PredictionRecord.src_ip`'s docstring) or enrichment
    hasn't completed yet (dispatched asynchronously, see
    `nids.api.threat_intel.dispatcher`). Only a nonexistent prediction id
    is a 404."""
    view = get_prediction(db_engine, prediction_id)
    if view is None:
        raise HTTPException(status_code=404, detail=f"No prediction found with id {prediction_id!r}.")
    indicators = [ip for ip in (view.src_ip, view.dst_ip) if ip]
    cached = list_enrichments_for_indicators(db_engine, indicators)
    return EnrichmentListResponse(items=_enrichment_items_for(view, cached))


@router.get("/alerts/{alert_id}/enrichment", response_model=EnrichmentListResponse)
def get_alert_enrichment_route(
    alert_id: str, db_engine: DbEngineDep, _current_user: CurrentUserDep
) -> EnrichmentListResponse:
    """Thin convenience wrapper: resolves `alert.prediction_id`, then
    returns exactly what `GET /history/predictions/{id}/enrichment`
    would -- an indicator's reputation is a property of the flow (the
    prediction), not of the alert raised about it, so this never
    duplicates storage or logic, just the lookup path a dashboard already
    sitting on an alert row would otherwise need a second round trip for."""
    alert_view = get_alert(db_engine, alert_id)
    if alert_view is None:
        raise HTTPException(status_code=404, detail=f"No alert found with id {alert_id!r}.")
    prediction_view = get_prediction(db_engine, alert_view.prediction_id)
    if prediction_view is None:
        # Shouldn't happen (alerts always reference a real prediction_id --
        # PredictionRecord.alerts is cascade="all, delete-orphan"), but an
        # orphaned alert should still 200 with no enrichment, not 500.
        return EnrichmentListResponse(items=[])
    indicators = [ip for ip in (prediction_view.src_ip, prediction_view.dst_ip) if ip]
    cached = list_enrichments_for_indicators(db_engine, indicators)
    return EnrichmentListResponse(items=_enrichment_items_for(prediction_view, cached))


@router.get("/audit", response_model=AuditEventResponse)
def list_audit_events_route(
    db_engine: DbEngineDep,
    _current_user: CurrentUserDep,
    event_type: str | None = None,
    actor: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = _LimitQuery,
    offset: int = _OffsetQuery,
) -> AuditEventResponse:
    page = list_audit_events(
        db_engine,
        event_type=event_type,
        actor=actor,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    return AuditEventResponse(
        items=[_to_audit_event_item(i) for i in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )
