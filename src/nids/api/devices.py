"""Admin-only device management: list paired devices and revoke one.
Exposes `nids.api.store.revoke_device` (existing since Milestone 6, never
routed) and a new `list_devices` over HTTP for the first time -- closes
`docs/DASHBOARD.md`'s "no cap and no revocation UI" gap using code that
already exists and already has unit coverage.

A fifth `APIRouter` (see `history.py`/`ingest.py`/`broadcast.py`/
`auth.py`) -- kept separate from `ingest.py` (which owns pairing, an
agent-facing concern) since this is a browser/admin-facing concern with a
different auth model (`require_role("admin")`, not device-credential-based).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Request

from nids.api.auth import require_role
from nids.api.schemas import DeviceListItem, DeviceListResponse
from nids.api.store import (
    DeviceRecordView,
    UserRecordView,
    list_devices,
    record_audit_event,
    revoke_device,
)

router = APIRouter(prefix="/devices")

AdminOnlyDep = Annotated[UserRecordView, require_role("admin")]


def _get_db_engine(request: Request):
    db_engine = getattr(request.app.state, "db_engine", None)
    if db_engine is None:
        raise HTTPException(
            status_code=503, detail="No database is configured for this deployment."
        )
    return db_engine


def _to_device_item(view: DeviceRecordView) -> DeviceListItem:
    return DeviceListItem(
        id=view.id,
        name=view.name,
        user_id=view.user_id,
        paired_at=view.paired_at,
        last_seen_at=view.last_seen_at,
        revoked=view.revoked,
    )


@router.get("", response_model=DeviceListResponse)
def list_devices_route(
    request: Request, _admin: AdminOnlyDep, limit: int = 20, offset: int = 0
) -> DeviceListResponse:
    db_engine = _get_db_engine(request)
    page = list_devices(db_engine, limit=limit, offset=offset)
    return DeviceListResponse(
        items=[_to_device_item(d) for d in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post("/{device_id}/revoke", response_model=DeviceListItem)
def revoke_device_route(device_id: str, request: Request, admin: AdminOnlyDep) -> DeviceListItem:
    db_engine = _get_db_engine(request)
    view = revoke_device(db_engine, device_id)
    if view is None:
        raise HTTPException(status_code=404, detail=f"No device found with id {device_id!r}.")
    record_audit_event(
        db_engine, event_type="device_revoked", actor=f"user:{admin.username}", target_id=device_id
    )
    return _to_device_item(view)
