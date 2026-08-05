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
   |        /history/predictions /history/alerts /agent/pair*
   |  WS:   /ws/live?token=<device-token>
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
| `frontend/src/hooks/useLiveFeed.ts` | Owns the `/ws/live` WebSocket: reconnect + backoff, REST backfill |
| `frontend/src/hooks/useDeviceAuth.ts` | Lazy device pairing, token persisted in `localStorage` |
| `frontend/src/context/DeviceAuthProvider.tsx` | The one piece of app-wide client state (the device token) |
| `frontend/src/routes/*.tsx` | The five pages — see "Pages" below |

State management: TanStack Query owns every piece of server state
(history, alerts, model info, health); there is no Redux/Zustand — see
"Why not alternatives".

## Auth model

There is no real user-login system anywhere in this backend (see
`docs/LIVE_MONITORING.md`'s own note on `/ws/live`'s auth, which this
reuses verbatim). The dashboard stands in with the same agent-pairing
flow a capture agent uses: on first visit to a page that needs it (Live
Feed, Alerts, or History), `useDeviceAuth` calls `POST /agent/pair` then
`POST /agent/pair/exchange` with `device_name: "dashboard-web"`, and
persists the returned bearer token in `localStorage`. That token becomes
the `?token=` on `/ws/live`. Pairing is **lazy, not eager** — Manual
Predict and CSV Upload never trigger it, and a browser tab that only
visits those two pages never creates a `devices` row. This is a
pragmatic stand-in, not multi-user auth: every browser instance that
does visit a data page becomes its own unauthenticated "device," with no
cap and no revocation UI. Fixing that for real needs actual per-user
accounts, which don't exist in this backend today (see `docs/API.md`'s
"Future endpoints" — "Multi-user deployments").

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

## Why not alternatives

- **No Redux/Zustand.** TanStack Query already owns all server state;
  the only genuinely global client state is the device token, which is
  one small React Context (`DeviceAuthProvider`), not a state library.
- **No `socket.io-client`.** `/ws/live` is a plain FastAPI `WebSocket`,
  not a Socket.IO server — a Socket.IO client would speak the wrong
  protocol entirely. `useLiveFeed` wraps the native `WebSocket` API
  instead, mirroring `src/nids/agent/client.py`'s `AgentClient` reconnect
  philosophy (exponential backoff + jitter) in the frontend's own
  language.
- **Eager pairing on app mount, rejected.** `POST /agent/pair` /
  `/agent/pair/exchange` are now rate-limited per client IP (Milestone 10
  — see [`docs/OBSERVABILITY.md`](OBSERVABILITY.md#rate-limiting)) but
  still have no auth by design (see "Auth model" above) — a device has
  nothing to authenticate with before pairing succeeds. Pairing on every
  mount would still create a `devices` row for every browser tab that
  ever opens the app, including ones that only ever use Manual Predict,
  and would burn through the rate limit faster than necessary. Lazy
  pairing — only when a data page is actually visited — is the smaller
  footprint for the same capability.
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
