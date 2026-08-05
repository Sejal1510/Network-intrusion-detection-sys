"""Agent pairing + WebSocket ingestion: the boundary between a live
capture agent (`nids.agent`, running on a user's own machine) and the
internal `MessageBus` (`nids.api.bus`). Nothing here runs prediction
logic -- it authenticates, validates the raw-record shape, and publishes
to the `"flows"` channel; `nids.api.worker` (consuming that channel) is
what calls `nids.api.pipeline.process_record`.

The agent authenticates its `/agent/ingest` connection via a proper
`Authorization: Bearer <token>` handshake header -- it's a Python client,
not a browser, so it isn't subject to the header restriction that makes
`/ws/live` (see `nids.api.broadcast`) use a query-param token instead.
"""

from __future__ import annotations

import logging
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect

from nids.api.agent_auth import (
    DEFAULT_PAIRING_TTL_SECONDS,
    authenticate_device,
    exchange_pairing_token,
    issue_pairing_token,
)
from nids.api.auth import OptionalCurrentUserDep
from nids.api.config import ServingConfig
from nids.api.schemas import DeviceCredentialResponse, PairingExchangeRequest, PairingTokenResponse
from nids.api.store import record_audit_event
from nids.features.contracts import validate_raw_records

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent")


def _get_db_engine(request: Request):
    db_engine = getattr(request.app.state, "db_engine", None)
    if db_engine is None:
        raise HTTPException(
            status_code=503, detail="No database is configured for this deployment."
        )
    return db_engine


async def _enforce_pairing_rate_limit(request: Request) -> None:
    config: ServingConfig = request.app.state.serving_config
    limiter = request.app.state.rate_limiter
    client_host = request.client.host if request.client else "unknown"
    key = f"pairing:{client_host}"
    if not await limiter.allow(key, limit=config.pairing_rate_limit_per_minute, window_seconds=60):
        logger.warning("Rate limit exceeded: scope=pairing client=%s", client_host)
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")


PairingRateLimitDep = Annotated[None, Depends(_enforce_pairing_rate_limit)]


@router.post("/pair", response_model=PairingTokenResponse)
def pair(request: Request, _rate_limit: PairingRateLimitDep) -> PairingTokenResponse:
    """Issue a short-lived pairing token. Stateless -- works even without
    a database configured (see `nids.api.agent_auth`)."""
    token = issue_pairing_token(request.app.state.secret_key)
    return PairingTokenResponse(pairing_token=token, expires_in_seconds=DEFAULT_PAIRING_TTL_SECONDS)


@router.post("/pair/exchange", response_model=DeviceCredentialResponse)
def pair_exchange(
    payload: PairingExchangeRequest,
    request: Request,
    _rate_limit: PairingRateLimitDep,
    current_user: OptionalCurrentUserDep,
) -> DeviceCredentialResponse:
    """Redeem a pairing token for a long-lived device credential. Needs a
    database (the credential is persisted). If the caller carries a
    valid login session (e.g. a logged-in dashboard tab), the new
    device's `user_id` is set to that user -- entirely optional, since
    `exchange_pairing_token`/`register_device` have accepted `user_id`
    since Milestone 6 with no caller ever populating it. Pairing from an
    anonymous tab or the live-capture agent's CLI (which never sends a
    session `Authorization` header) is unaffected."""
    db_engine = _get_db_engine(request)
    client_host = request.client.host if request.client else "unknown"
    try:
        credential = exchange_pairing_token(
            db_engine,
            payload.pairing_token,
            request.app.state.secret_key,
            payload.device_name,
            user_id=current_user.id if current_user is not None else None,
        )
    except ValueError as exc:
        record_audit_event(
            db_engine, event_type="device_pair_failed", actor=client_host, detail=str(exc)
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_audit_event(
        db_engine, event_type="device_paired", actor=client_host, target_id=credential.device_id
    )
    return DeviceCredentialResponse(device_id=credential.device_id, token=credential.token)


@router.websocket("/ingest")
async def ingest(websocket: WebSocket) -> None:
    """One flow record (a JSON object satisfying `FEATURE_COLUMNS`) per
    WebSocket text message. Each valid record is published to the
    `"flows"` bus channel, tagged with the authenticated device's id;
    each invalid one gets an error message back and is otherwise dropped
    -- never fatal to the connection (a single bad flow shouldn't end
    monitoring)."""
    db_engine = getattr(websocket.app.state, "db_engine", None)
    if db_engine is None:
        await websocket.close(code=1008, reason="No database is configured for this deployment.")
        return

    auth_header = websocket.headers.get("authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    device = authenticate_device(db_engine, token) if token else None
    if device is None:
        await websocket.close(code=1008, reason="Invalid or revoked device credential.")
        return

    await websocket.accept()
    bus = websocket.app.state.bus

    try:
        while True:
            record = await websocket.receive_json()
            try:
                validate_raw_records(pd.DataFrame([record]))
            except ValueError as exc:
                await websocket.send_json({"type": "error", "detail": str(exc)})
                continue
            await bus.publish("flows", {"device_id": device.id, "record": record})
    except WebSocketDisconnect:
        pass
