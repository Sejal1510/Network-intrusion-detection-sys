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

import pandas as pd
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from nids.api.agent_auth import (
    DEFAULT_PAIRING_TTL_SECONDS,
    authenticate_device,
    exchange_pairing_token,
    issue_pairing_token,
)
from nids.api.schemas import DeviceCredentialResponse, PairingExchangeRequest, PairingTokenResponse
from nids.features.contracts import validate_raw_records

router = APIRouter(prefix="/agent")


def _get_db_engine(request: Request):
    db_engine = getattr(request.app.state, "db_engine", None)
    if db_engine is None:
        raise HTTPException(
            status_code=503, detail="No database is configured for this deployment."
        )
    return db_engine


@router.post("/pair", response_model=PairingTokenResponse)
def pair(request: Request) -> PairingTokenResponse:
    """Issue a short-lived pairing token. Stateless -- works even without
    a database configured (see `nids.api.agent_auth`)."""
    token = issue_pairing_token(request.app.state.secret_key)
    return PairingTokenResponse(pairing_token=token, expires_in_seconds=DEFAULT_PAIRING_TTL_SECONDS)


@router.post("/pair/exchange", response_model=DeviceCredentialResponse)
def pair_exchange(payload: PairingExchangeRequest, request: Request) -> DeviceCredentialResponse:
    """Redeem a pairing token for a long-lived device credential. Needs a
    database (the credential is persisted)."""
    db_engine = _get_db_engine(request)
    try:
        credential = exchange_pairing_token(
            db_engine, payload.pairing_token, request.app.state.secret_key, payload.device_name
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
