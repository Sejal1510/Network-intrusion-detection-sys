# Live Monitoring: Agent, MessageBus, and Streaming

**Status: Milestone 6.** Turns the two "Future endpoints" named in
[`docs/API.md`](API.md) — live packet capture and WebSockets/streaming —
into a working pipeline. Nothing about `/predict`, `/predict/batch`, the
History API, or persistence changes: a live flow runs through the exact
same `nids.api.pipeline.process_record` an HTTP `/predict` call does,
just triggered by a bus message instead of a request. `source` on every
persisted prediction/alert is `"agent"` for these, `"api"` for HTTP
callers — the schema slot `docs/DATABASE.md` reserved for this milestone,
unused until now.

## Architecture

```
nids.agent (user's machine)                    nids.api (server)
--------------------------                     ------------------
FlowSource                                     /agent/ingest (WebSocket)
  LiveCapture --\                                |  authenticate_device()
  ReplaySource --+--> FlowAggregator --records-->|  validate_raw_records()
                 /                               v
                                              MessageBus "flows" channel
                                                  |
AgentClient                                       v  nids.api.worker
  bounded ring buffer                          process_record()  <- SAME
  reconnect + exponential backoff                 |                pipeline
                                                   v                /predict
                                              MessageBus "live" channel  uses
                                                   |
                                              /ws/live (WebSocket)  <--- dashboard
                                                  broadcast every result
```

Two WebSocket endpoints, two different auth mechanisms, for a reason
documented at each:

- **`/agent/ingest`** (`nids.api.ingest`) — the agent is a Python client,
  not a browser, so it authenticates with a proper
  `Authorization: Bearer <device-token>` handshake header.
- **`/ws/live`** (`nids.api.broadcast`) — a browser dashboard can't set
  custom handshake headers on a WebSocket, so it authenticates via a
  `?token=` query parameter instead, the standard pragmatic pattern for
  browser-facing WebSocket auth. Both reuse the same device-credential
  check (`nids.api.agent_auth.authenticate_device`) — a pragmatic
  stand-in gate, not real multi-user session auth (still a later,
  separate concern — see `docs/API.md`'s "Future endpoints").

## Pairing: two credentials, two lifetimes

`nids.api.agent_auth` issues two distinct credentials rather than one,
because they have genuinely different lifetime and storage requirements:

| | Pairing token | Device credential |
|---|---|---|
| Lifetime | ~10 minutes | Indefinite (revocable) |
| Storage | None — stateless, HMAC-signed (`itsdangerous`) | `devices` table (`nids.api.store`); only a hash is stored |
| Purpose | Prove "I'm allowed to add a device right now" | Authenticate every future `/agent/ingest` connection |

Flow: `POST /agent/pair` issues a pairing token with no database required
(it's self-contained and signed); a human copies that code to the machine
that will run the agent and redeems it via
`python -m nids.agent pair <code>`, which calls `POST
/agent/pair/exchange` and gets back a long-lived bearer token, persisted
locally (`nids.agent.cli.save_device_credential`) so it never needs to be
re-entered. `python -m nids.agent run` reads that saved credential and
starts streaming.

## The agent (`src/nids/agent/`)

- **`capture.py` — `LiveCapture`.** Wraps Scapy's `AsyncSniffer`, bridging
  its synchronous, background-thread packet callback into an
  `asyncio.Queue` via `call_soon_threadsafe` — the standard thread-to-
  asyncio pattern. Needs elevated privileges (Administrator + Npcap on
  Windows, root/`CAP_NET_RAW` on Linux/Mac), documented rather than
  worked around, matching the constraint `legacy/app.py`'s own capture
  already had.
- **`sources.py` — `LiveSource` / `ReplaySource`.** Both satisfy the same
  `FlowSource` protocol and share the *same* `FlowAggregator`
  (`nids.flows.aggregator`) that turns a `PacketEvent` stream into flow
  records satisfying `FEATURE_COLUMNS` — reused unchanged, not
  reimplemented, from `nids.flows.pcap`'s file-based extraction.
  `ReplaySource` replays a saved `.pcap` at a configurable `speed`
  (`1.0` = real inter-arrival timing, higher = accelerated demo,
  `None` = as fast as possible — used for the manual verification below
  and for tests, since it needs neither root nor real traffic).
  `AgentClient` doesn't know or care which source it's fed by.
- **`client.py` — `AgentClient`.** Exchanges a pairing token for a device
  credential, then owns the outbound WebSocket connection: `_produce()`
  drains a `FlowSource` into a bounded ring buffer (`deque(maxlen=...)`,
  drop-oldest on overflow — live monitoring favors recency/availability
  over perfect historical completeness); `_send_loop()` drains that
  buffer to the server, reconnecting with exponential backoff + jitter,
  retried indefinitely, since the agent is meant to run unattended. The
  two run concurrently via `run()` so capture never blocks on network I/O.
- **`cli.py` / `__main__.py` — `python -m nids.agent`.** `pair <code>`
  redeems a pairing code and persists the resulting device credential;
  `run` builds a `LiveSource` or `ReplaySource` (`--pcap` selects replay)
  and starts `AgentClient.run()`. Kept out of `nids/agent/__init__.py`'s
  import graph so `python -m nids.agent` doesn't re-import its own module
  as `__main__` — the same reasoning `nids.api.cli`/`nids.training.cli`
  already established.

## MessageBus (`nids.api.bus`)

The internal transport between ingestion, the worker, and dashboard
broadcast — one `Protocol`, two implementations, the same "swap the
backend without changing the interface" pattern `nids.api.store` already
uses for `database_url`:

- **`InMemoryBus`** (default, no `redis_url`): `asyncio.Queue`-based, zero
  new infrastructure. `create_app` runs the worker as a background task in
  the same process — how a single local/dev deployment runs today.
- **`RedisBus`** (opt-in, `redis_url` set): **Streams** for `"flows"`
  (durable, at-least-once, consumer-group scalable — an agent's flow
  survives a worker restart) and **Pub/Sub** for `"live"` (ephemeral,
  zero storage; a disconnected dashboard catches up via the existing
  History API, not bus replay). Two different Redis primitives for two
  different reliability requirements, not one primitive reused
  everywhere. `nids.api.bus` is the only module that imports `redis`,
  mirroring `nids.api.store` being the only one that imports `sqlalchemy`.

`nids.api.worker.run_worker` consumes `"flows"` one message at a time and
calls `process_record` — explaining (`SHAP`) only alert-worthy flows by
default (`explain_only_alert_worthy`), since running an explainer for
every live flow would make explainability a throughput bottleneck for the
large majority of normal traffic that never becomes an alert. A single
record's failure is logged and dropped, never fatal to the loop — one bad
flow from one device must not stop monitoring for every device.

## Why not alternatives

- **MQTT / Kafka for agent ingestion.** Real message-broker protocols,
  but this milestone's actual requirement — one agent process holding one
  long-lived connection to one server, sending small JSON records — is
  exactly what a WebSocket already does, with the added benefit of one
  fewer piece of infrastructure to run. `RedisBus` (Streams) is the named
  upgrade path if durability/consumer-group scaling is ever needed on the
  *internal* `"flows"` channel; it doesn't change what the agent speaks
  over the wire.
- **mTLS for agent auth.** The more "enterprise" answer, but it needs a
  private CA and certificate lifecycle management neither this project
  nor its target deployment scale has today. Bearer-token pairing gets
  the same practical property (only a paired device can stream) with
  infrastructure this platform already has (`itsdangerous`, already a
  dependency; a `devices` table, the same pattern as `predictions`/
  `alerts`).
- **A single WebSocket for both agent ingestion and dashboard fan-out.**
  Rejected because the two have different auth surfaces (custom header
  vs. browser-safe query param) and different message directions
  (agent -> server vs. server -> dashboard) — collapsing them would mean
  branching on connection role inside one handler instead of two small,
  single-purpose routes.

## Reproducing / running it end-to-end

```bash
# 1. Start the server (add --database-url to persist agent predictions/alerts
#    like any other source; the WS routes need one, since device auth reads
#    it -- see nids.api.agent_auth)
python -m nids.api --run-id <run_id> --database-url sqlite:///history.db

# 2. Issue a pairing code (stands in for a future dashboard "add device" button)
curl -X POST http://localhost:8000/agent/pair

# 3. On the machine that will run the agent, redeem it once
python -m nids.agent pair <pairing_token> \
    --base-url http://localhost:8000 --device-name my-laptop

# 4a. Stream real local traffic (needs elevated privileges -- see capture.py)
python -m nids.agent run --base-url http://localhost:8000

# 4b. ...or replay a saved capture instead (no privileges needed)
python -m nids.agent run --base-url http://localhost:8000 \
    --pcap path/to/capture.pcap --speed 1000
```

Watch the results arrive by connecting to `/ws/live?token=<device-token>`
with any WebSocket client — each message is
`{"type": "prediction", "data": <the same shape /predict returns>}`.
This exact sequence (steps 1–4b, replaying
`tests/fixtures/sample_capture.pcap`) was used to manually verify the full
pipeline end-to-end: agent -> ingest -> `"flows"` -> worker -> pipeline ->
`"live"` -> broadcast, confirming real predictions arrive on `/ws/live`.

## Testing

Real capture/replay needs a NIC, elevated privileges, or a `.pcap` file —
none of which CI has on demand — so every layer is tested against a stub
satisfying the same protocol/interface the real thing does, the pattern
already established for `Classifier`/`MessageBus`/etc.:

- `tests/test_agent_capture.py` — `LiveCapture` against a stub `AsyncSniffer`.
- `tests/test_agent_sources.py` — `LiveSource`/`ReplaySource` against a stub
  `Capture` and a real fixture `.pcap`.
- `tests/test_agent_client.py` — `AgentClient` against a stub `FlowSource`
  and a stub WebSocket connection (buffering, backoff/reconnect,
  drop-oldest overflow).
- `tests/test_agent_cli.py` — argument parsing, credential persistence,
  and source selection, with `AgentClient`/`asyncio.run` stubbed out so
  tests don't actually open a socket or run forever.
- `tests/test_api_agent_auth.py`, `tests/test_api_ingest.py`,
  `tests/test_api_broadcast.py` — pairing, device auth, and both WebSocket
  routes against FastAPI's `TestClient`.
