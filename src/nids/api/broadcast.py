"""WebSocket broadcast: streams live prediction results to dashboard
clients, subscribing to the `MessageBus` `"live"` channel
`nids.api.worker` publishes to.

Browser WebSockets can't set custom handshake headers the way
`nids.api.ingest`'s agent-facing endpoint does, so `/ws/live`
authenticates via a query-param token instead -- but unlike a REST
route's `Authorization` header, anything on the URL can end up in
proxy/access logs for as long as that token stays valid. So the token
here is never the long-lived dashboard session itself, nor (as before
this module's Milestone 15 rework) a non-expiring device credential --
it's a `nids.api.user_auth.issue_ws_ticket`/`verify_ws_ticket` ticket:
minted fresh by the *logged-in* dashboard user immediately before each
connect/reconnect (`POST /auth/ws-ticket`, login-gated same as every
other dashboard route) and valid for only ~60 seconds. This is the same
real session identity every other gated route trusts, just handed to
this one handshake through a short-lived proxy instead of a header
browsers can't set -- not a separate, parallel auth system the way the
device-credential stand-in used to be.

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

from nids.api.user_auth import verify_ws_ticket

router = APIRouter()


@router.websocket("/ws/live")
async def live(websocket: WebSocket, ticket: str = Query(...)) -> None:
    db_engine = getattr(websocket.app.state, "db_engine", None)
    if db_engine is None:
        await websocket.close(code=1008, reason="No database is configured for this deployment.")
        return

    user_id = verify_ws_ticket(ticket, websocket.app.state.secret_key)
    if user_id is None:
        await websocket.close(code=1008, reason="Invalid or expired ticket.")
        return

    await websocket.accept()
    bus = websocket.app.state.bus

    try:
        async for message in bus.subscribe("live"):
            await websocket.send_json({"type": "prediction", "data": message})
    except WebSocketDisconnect:
        pass
