"""WebSocket broadcast: streams live prediction results to dashboard
clients, subscribing to the `MessageBus` `"live"` channel
`nids.api.worker` publishes to.

Browser WebSockets can't set custom handshake headers the way
`nids.api.ingest`'s agent-facing endpoint does, so `/ws/live`
authenticates via a query-param token instead -- the standard, pragmatic
pattern for browser-facing WebSocket auth. It reuses the same device
credentials `nids.api.agent_auth.authenticate_device` already verifies
(a pragmatic stand-in gate, not real multi-user session auth, which
doesn't exist anywhere in this project yet -- a separate, later concern
noted in `docs/API.md`'s "Future endpoints").

Catch-up on reconnect is the dashboard client's job, via the existing
`nids.api.history` REST API -- this channel is deliberately ephemeral
(Pub/Sub semantics: "new events from now"), not a replay log; see
`nids.api.bus`'s module docstring for why.

Each message is wrapped `{"type": "prediction", "data": <PredictResponse
dict>}`. A `PredictResponse` already carries `alert_id`/`severity`/
`risk_score`, so a dashboard can tell an alert-worthy prediction from an
ordinary one without a second, separately-published "alert" message --
one message type, not two publishes per flow. Rolling statistics
(predictions/sec, alert rate, ...) are left to the dashboard client to
derive from this same stream rather than a server-computed "stats"
channel -- simpler, and every dashboard client can already see every
message needed to compute its own.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from nids.api.agent_auth import authenticate_device

router = APIRouter()


@router.websocket("/ws/live")
async def live(websocket: WebSocket, token: str = Query(...)) -> None:
    db_engine = getattr(websocket.app.state, "db_engine", None)
    if db_engine is None:
        await websocket.close(code=1008, reason="No database is configured for this deployment.")
        return

    device = authenticate_device(db_engine, token)
    if device is None:
        await websocket.close(code=1008, reason="Invalid or revoked credential.")
        return

    await websocket.accept()
    bus = websocket.app.state.bus

    try:
        async for message in bus.subscribe("live"):
            await websocket.send_json({"type": "prediction", "data": message})
    except WebSocketDisconnect:
        pass
