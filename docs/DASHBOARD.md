# Web Dashboard

**Status: Milestone 7.** Gives the platform its first real frontend.
Milestones 1–6 built a full prediction/explainability/security-
intelligence/live-streaming backend (see [`docs/API.md`](API.md) and
[`docs/LIVE_MONITORING.md`](LIVE_MONITORING.md)) with no consumer of any
of it beyond `curl` and raw WebSocket clients — `/ws/live` streamed real
predictions and alerts that nobody could actually see. This milestone
closes that gap: `frontend/` is a React + Vite single-page app that
renders the exact same data every prior milestone already produces.
Nothing on the backend changes shape; three small additive endpoints/
fields were added purely because the dashboard needed them (CORS
opt-in, `GET /mitre`, `HealthResponse.database_configured` — see
[`docs/API.md`](API.md)).

## Architecture

```
Browser (frontend/, Vite dev server or static build)
   |
   |  REST: /health /model /mitre /predict /predict/batch
   |        /history/predictions /history/alerts
   |        /auth/login /auth/logout /auth/me /auth/ws-ticket
   |  WS:   /ws/live?ticket=<short-lived ws-ticket, see docs/AUTH.md>
   v
FastAPI (nids/api/, unchanged shape -- see docs/API.md)
```

No CORS is enabled by default (see `docs/API.md`'s "CORS" section) — the
dashboard's dev server (`localhost:5173`) and the API (`localhost:8000`)
are different origins, so the server must be started with
`--cors-origin http://localhost:5173` for local development.

| Module | Responsibility |
|---|---|
| `frontend/src/api/types.ts` | Hand-written TS mirrors of `nids/api/schemas.py`, field-for-field |
| `frontend/src/api/client.ts` | `fetch` wrapper: base URL, JSON/FormData handling, `ApiError` |
| `frontend/src/api/endpoints/*.ts` | One thin function per backend route |
| `frontend/src/hooks/useLiveFeed.ts` | Owns the `/ws/live` WebSocket: mints a fresh ws-ticket per (re)connect, reconnect + backoff, REST backfill |
| `frontend/src/hooks/useUserAuth.ts` / `context/UserAuthProvider.tsx` | Dashboard login session -- also the identity behind `/ws/live` (see "Auth model") |
| `frontend/src/routes/*.tsx` | The five pages — see "Pages" below |

State management: TanStack Query owns every piece of server state
(history, alerts, model info, health); there is no Redux/Zustand — see
"Why not alternatives".

## Auth model

Full design (session model, CORS, CSP) lives in
[`docs/AUTH.md`](AUTH.md); the short version for how the dashboard uses
it: every page except Login sits behind `RequireAuth`, which redirects
to `/login` until `POST /auth/login` succeeds and persists a session
token (`localStorage`, `nids_session_token`). That same token is
attached as `Authorization: Bearer <token>` to every REST call
(`api/client.ts`).

`/ws/live` is the one exception a plain `Authorization` header can't
reach — browsers don't let `WebSocket` set custom handshake headers.
Rather than fall back to a separate, longer-lived credential (device
pairing used to fill this gap, before real dashboard login existed),
`useLiveFeed` mints a short-lived **ws-ticket** (`POST /auth/ws-ticket`,
itself login-gated) immediately before every connect and reconnect, and
passes *that* as `/ws/live?ticket=`. The ticket expires in ~60 seconds
and carries only a user id — so a dead session simply fails to mint a
new one (reconnect attempts fail closed), and whatever lands in a proxy
access log is stale within about a minute. Logging out doesn't need to
explicitly tear down an open live socket either: `status` flipping to
`"anonymous"` makes `RequireAuth` redirect immediately, which unmounts
whatever page held the connection and runs `useLiveFeed`'s cleanup.

Device credentials (`POST /agent/pair` / `/agent/pair/exchange`) still
exist and are unrelated to any of this — they authenticate the actual
live-capture agent (`nids.agent`, a separate process, possibly on a
different machine) against `/agent/ingest`, never the dashboard.

## Degraded mode

`GET /health`'s `database_configured` field tells the dashboard upfront
whether `--database-url` was passed at startup, instead of discovering
it by a failed request:

| Page | Needs a database? | Behavior without one |
|---|---|---|
| Overview / Live Feed | Yes (`/ws/live`, `/history/predictions` backfill) | `DegradedModeBanner` shown, feed stays empty |
| Alerts | Yes (`/history/alerts`) | `DegradedModeBanner` shown, `503` surfaced |
| History | Yes (`/history/predictions`) | `DegradedModeBanner` shown, `503` surfaced |
| Manual Predict | No (`/predict` only) | Fully functional |
| CSV Upload | No (`/predict/batch` only) | Fully functional |

## Pages

Rebuilds the old prototype's four tabs (`templates/index.html`, now
unused — the original scripts live in `legacy/`) as five modern pages,
minus the old start/stop-local-capture control (superseded by the
separate `python -m nids.agent` process):

- **Overview** (old "Dashboard" tab) — stat tiles (total/normal/attacks/
  safety score), a severity-distribution bar chart, a predictions-over-
  time chart with alert markers, and the live feed table — all computed
  client-side from `useLiveFeed`'s in-memory buffer (last 500 messages,
  drop-oldest). `/ws/live` is Pub/Sub-only with no replay, so every
  reconnect backfills the gap via `GET /history/predictions?start_date=`.
- **Alerts** (old "recent security alerts" list) — `/history/alerts`,
  filterable by severity/acknowledged, paginated, with an acknowledge
  action wired to `POST /history/alerts/{id}/acknowledge`.
- **History** (new — the old prototype had no persisted-history view) —
  `/history/predictions`, filterable by severity/attack_category,
  paginated.
- **Manual Predict** (old "Manual Input" tab) — a form for all 41
  `FEATURE_COLUMNS` (`manualPredictFieldConfig.ts`, one source of truth
  for labels/defaults/groups), `POST /predict?explain=`, rendering the
  full response including a SHAP contribution bar chart when requested.
- **CSV Upload** (old "CSV Upload" tab) — drag/drop, `POST
  /predict/batch`, a summary panel with per-protocol breakdown and a
  top-10-most-dangerous table. **Design note:** `PredictResponse` (what
  `/predict/batch` returns per row) carries no `raw_record` — only a
  persisted `PredictionHistoryItem` does. Rather than add a redundant
  field to `PredictResponse` (the caller already has what it submitted),
  the frontend parses the uploaded CSV client-side (`lib/csv.ts`,
  PapaParse) and zips row `i` with `results[i]` by array index — safe
  only because `/predict/batch` is documented (and its route code
  confirms) to score rows in upload order.

### Pages added since Milestone 7

- **Login** (Milestone 11) — `POST /auth/login`, redirects to wherever
  `RequireAuth` bounced the visitor from.
- **Devices** (Milestone 11, admin-only) — `GET /devices` +
  `POST /devices/{id}/revoke`, the same list/action shape as Alerts'
  acknowledge button.
- **Audit Log** (Milestone 14, any authenticated user, not admin-gated —
  matches `/history/audit`'s own auth level) — `GET /history/audit`,
  filterable by event type/actor, paginated. Every login, device pairing/
  revocation, and alert acknowledgement the server has recorded.
- **Metrics** (Milestone 14, any authenticated user) — `GET
  /metrics/summary`, a JSON-friendly read of the same counters `GET
  /metrics` exposes in Prometheus text format, so the dashboard doesn't
  need a Prometheus/Grafana stack to show them. Stat tiles plus two bar
  charts (alerts by source, notification delivery by channel). Full
  design in [`docs/OBSERVABILITY.md`](OBSERVABILITY.md).
- **Overview** also gained a "Detection rules armed" panel (Milestone
  14) — `GET /rules`, listing every configured signature (id, name,
  severity, description) so an analyst can see what's armed without
  reading `detection_rules.yaml` directly. Full design in
  [`docs/RULES.md`](RULES.md).

## Why not alternatives

- **No Redux/Zustand.** TanStack Query already owns all server state;
  the only genuinely global client state is the login session, which is
  one small React Context (`UserAuthProvider`), not a state library.
- **No `socket.io-client`.** `/ws/live` is a plain FastAPI `WebSocket`,
  not a Socket.IO server — a Socket.IO client would speak the wrong
  protocol entirely. `useLiveFeed` wraps the native `WebSocket` API
  instead, mirroring `src/nids/agent/client.py`'s `AgentClient` reconnect
  philosophy (exponential backoff + jitter) in the frontend's own
  language.
- **A short-lived ws-ticket over reusing the session token directly,
  rejected.** The obvious simplest option for `/ws/live` was putting the
  real session token straight on the URL as `?token=`. Rejected because
  anything on a URL can end up in proxy/access logs for as long as that
  token stays valid — for an 8-hour session token, that's a real window.
  A ~60-second, single-purpose ticket (see "Auth model") gets the same
  practical effect (this handshake is authenticated as a real, currently
  logged-in user) while bounding how long a logged value stays useful.
  Full rationale in [`docs/AUTH.md`](AUTH.md).
- **Client-side CSV zip over a new backend field.** See the CSV Upload
  design note above.

## Reproducing / running it end-to-end

```bash
# 1. Backend: CORS for the Vite dev server, persistence on, a low
#    threshold so alerts actually fire during a demo
python -m nids.api --run-id <run_id> --artifact-root models/runs \
  --database-url sqlite:///history.db --alert-threshold 50 \
  --cors-origin http://localhost:5173 --port 8000

# 2. Frontend
cd frontend
npm install
npm run dev   # http://localhost:5173

# 3. Real traffic, via the existing capture agent (see docs/LIVE_MONITORING.md)
curl -X POST http://localhost:8000/agent/pair
python -m nids.agent pair <pairing_token> --base-url http://localhost:8000 --device-name demo-agent
python -m nids.agent run --base-url http://localhost:8000 \
  --pcap tests/fixtures/sample_capture.pcap --speed 1000
```

Then, in the browser: Overview's live feed and charts populate as the
agent replays; killing and restarting the backend shows
`ConnectionStatusIndicator` move live -> reconnecting -> live with no
gap in the table (REST backfill closes it); acknowledging an alert
persists across a refresh; Manual Predict with "Explain this
prediction" checked shows the SHAP bar chart; a CSV upload from
`data/processed/` shows the summary/breakdown/top-10 table; restarting
the backend **without** `--database-url` shows `DegradedModeBanner` on
Overview/Alerts/History while Manual Predict/CSV Upload keep working.

## Testing

Frontend tests are co-located `*.test.ts(x)` files (standard JS
convention, not the Python side's flat `tests/` dir), run via `npm test`
in `frontend/`. Scoped, not exhaustive — chart pixel output, routing
minutiae, and CSS are not tested:

- `src/hooks/useLiveFeed.test.tsx` — the deepest test in the suite:
  connect/open, message buffering (newest-first, dedup by id), the
  500-entry drop-oldest cap, and reconnect-with-backoff-then-backfill
  against a fake `WebSocket`.
- `src/hooks/useDeviceAuth.test.ts` — no-token pairing flow, an existing
  token skipping pairing, and a `503` exchange moving to `"unavailable"`.
- `src/api/client.test.ts` — JSON/FormData request shaping and
  `ApiError` construction, via MSW.
- `src/lib/severity.test.ts` — table-driven severity-to-status mapping
  (mirrors `tests/test_api_severity.py`'s own style).
- `src/components/common/SeverityBadge.test.tsx`,
  `src/components/forms/PredictionResultCard.test.tsx`,
  `src/components/forms/ManualPredictForm.test.tsx` — component smoke
  tests: every severity renders icon+label (never color alone), a full
  `PredictResponse` fixture renders without throwing with `alert_id`
  present vs. `null`, and a valid form submission calls its handler with
  all 41 fields and the edited values.

Backend additions from this milestone are tested alongside their
existing modules, not in new files — see `docs/API.md`'s "Tests"
section: `tests/test_api_schemas.py`, `tests/test_api_mitre.py`,
`tests/test_api_app.py`, `tests/test_api_cli.py`.
