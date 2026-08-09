# Inference API

**Status:** Milestone 5 — Security Intelligence layer. Every prediction
is now classified, scored for anomaly, explained on request, given a
numeric risk score, mapped to MITRE ATT&CK (where possible), and
threshold-gated into an alert — and, when a database is configured, all
of it is persisted and queryable via the History API. Live packet capture
and WebSocket streaming are now done too (Milestone 6 — see
[`docs/LIVE_MONITORING.md`](LIVE_MONITORING.md)), and so is the web
dashboard that actually consumes all of the above (Milestone 7 — see
[`docs/DASHBOARD.md`](DASHBOARD.md)). Rate limiting, structured logging,
metrics, and a security-action audit trail are done too (Milestone 10 —
see [`docs/OBSERVABILITY.md`](OBSERVABILITY.md)); notification
integrations and threat intel feeds remain future milestones — see
[Future endpoints](#future-endpoints) for how they plug into this
architecture without restructuring it.

## Architecture

The API serves one required classifier run and one optional anomaly-
detector run (see [Training pipeline](../src/nids/training/)) as a single
prediction service. It adds no new persistence format, feature logic, or
model logic — the anomaly detector is trained, evaluated, and persisted
through the exact same platform as any classifier (Isolation Forest is
just another registered model — see
[Training pipeline: model registry](../src/nids/models/registry.py)); the
API is a thin HTTP adapter combining two ordinary runs' outputs.

```
Client (JSON / CSV upload)
   -> FastAPI route (nids/api/app.py)        HTTP concerns only:
                                              parse, validate, format, status codes
   -> Pydantic schema (nids/api/schemas.py)   request shape validation
   -> DataFrame of raw records
   -> nids.api.inference.predict_one/batch    pure, model-agnostic -- UNCHANGED since Milestone 3
        -> classifier.feature_engineer.transform()   REUSED
        -> classifier.model.predict/predict_proba()  REUSED -- prediction, confidence
        -> anomaly.feature_engineer.transform()      REUSED (own fitted pipeline)
        -> anomaly.model.anomaly_score()             normalized 0-1, higher = more anomalous
        -> severity.compute_severity()                pure rule function
   -> if ?explain=true:
        nids.api.explain.explain_one/batch          a SECOND, independent delegate --
             -> classifier.feature_engineer.transform()   never inside inference.py
             -> shap.TreeExplainer(classifier.model)        cached per served model
             -> Explanation(base_value, top_features, summary)
   -> nids.api.risk.compute_risk_score(PredictionResult)          ALWAYS runs, pure
   -> nids.api.mitre.map_to_mitre(PredictionResult.attack_category) ALWAYS runs, pure
        (both consume only PredictionResult fields -- independent of each
         other and of whether ?explain=true was used)
   -> nids.api.alerts.generate_alert(...)     threshold-gated (alert_threshold, default 70) --
                                               None below threshold, the common case
   -> if database_url configured:
        nids.api.store.save_prediction/save_alert    OPT-IN, off by default
   -> response schema -> JSON  (risk_score/mitre/alert_id always present; alert_id
                                 reflects whether an alert was RAISED, independent
                                 of whether persistence is even on)
```

If no anomaly detector is pinned, `anomaly_score`/`is_anomaly` are `null`
and `severity` is computed from classifier confidence alone — `/predict`
reproduces Milestone 2's behavior exactly. If `explain` is omitted or
`false` (the default), `explanation` is `null` and zero SHAP code runs —
`/predict` reproduces Milestone 3's behavior exactly. If `database_url`
is unset (the default), zero DB writes happen and every other field is
unaffected — `/predict` reproduces Milestone 4's behavior exactly, plus
the new always-on `risk_score`/`mitre`/`alert_id` fields.
`nids.api.inference` has never imported `shap` (or `sqlalchemy`) and
still doesn't; `explain.py`/`risk.py`/`mitre.py`/`alerts.py`/`store.py`
are independent delegates the route calls *alongside* it, never changes
inside it.

Both runs are loaded **once, at process startup**, via
`nids.training.artifacts.load_run` — the exact `(model, FeatureEngineer,
metrics, metadata)` each training run already produced. Which runs are
served are pinned `run_id`/`anomaly_run_id` in `ServingConfig`
(`nids/api/config.py`), not auto-selected "latest" runs: promoting a new
model to serve is an explicit, reviewable config change.

| Module | Responsibility |
|---|---|
| `nids/api/config.py` | `ServingConfig` — which run_id(s) to serve, and where |
| `nids/api/model_loader.py` | Load those runs into memory once (`ServedEnsemble`) |
| `nids/api/inference.py` | Pure `predict_one`/`predict_batch` — no HTTP awareness |
| `nids/api/severity.py` | Pure `compute_severity` rule table |
| `nids/api/explain.py` | Pure `explain_one`/`explain_batch` — SHAP, no HTTP awareness |
| `nids/api/risk.py` | Pure `compute_risk_score` — numeric 0-100 synthesis |
| `nids/api/mitre.py` | Pure `map_to_mitre` — data-driven ATT&CK lookup |
| `nids/api/alerts.py` | Pure `generate_alert` — threshold-gated |
| `nids/api/store.py` | SQLAlchemy persistence (opt-in) — see `docs/DATABASE.md` |
| `nids/api/history.py` | `/history/*` `APIRouter` — read access + alert acknowledgement |
| `nids/api/schemas.py` | Pydantic request/response contracts |
| `nids/api/app.py` | FastAPI routes — HTTP boundary only |
| `nids/api/cli.py` | `python -m nids.api --run-id ... [--anomaly-run-id ...] [--database-url ...] [--alert-threshold ...]` entrypoint |
| `nids/models/anomaly.py` | `IsolationForestClassifier` — Isolation Forest adapted to the `Classifier` protocol, plus `explainable_model` for SHAP |

## Endpoints

### `GET /health`

Liveness probe. Always returns `200` if the process is up; `model_loaded`
reports whether a served model is available.

**Response** (`HealthResponse`)
```json
{ "status": "ok", "model_loaded": true, "database_configured": true }
```
`database_configured` reports whether `--database-url` was passed at
startup — a dashboard checks this once instead of discovering it by
trial request, since `/history/*` and `/ws/live` both `503` without one
(see [`docs/DASHBOARD.md`](DASHBOARD.md) "Degraded mode").

### `GET /metrics`

Prometheus text exposition format — request counts/latency, prediction
latency, alerts raised. Unauthenticated, same as `/health`. Full metric
list and a caveat about `nids_prediction_duration_seconds`'s two route
labels not being apples-to-apples in
[`docs/OBSERVABILITY.md`](OBSERVABILITY.md#metrics).

### `GET /metrics/summary`

A JSON-friendly read of the same counters `/metrics` exposes in
Prometheus text format — for the dashboard's Metrics page (Milestone 14),
which has no Prometheus/Grafana stack to query `/metrics` itself.
Login-gated (unlike `/metrics`, which stays public for a real Prometheus
scraper). Full design in
[`docs/OBSERVABILITY.md`](OBSERVABILITY.md#metrics).

**Response** (`MetricsSummaryResponse`)
```json
{
  "http_requests_total": 42,
  "alerts_by_source": { "api": 5, "rule": 2 },
  "notifications_by_channel": { "SlackNotificationChannel": { "success": 3, "failure": 1 } },
  "predictions_by_route": { "/predict": 10 },
  "avg_prediction_duration_seconds": { "/predict": 0.057 }
}
```

### `GET /rules`

The configured signature-detection rules (`nids.api.rules`, Milestone
13) — so a dashboard can show which detections are armed, not just that
a past alert happened to say `source="rule"`. Login-gated: unlike
`/mitre` (pure reference data), knowing exact detection thresholds is
itself security-relevant information. Full design in
[`docs/RULES.md`](RULES.md).

**Response** (`list[RuleResponse]`)
```json
[
  {
    "id": "R001",
    "name": "SYN flood pattern",
    "description": "...",
    "severity": "critical",
    "conditions": [
      { "field": "flag", "operator": "eq", "value": "S0" },
      { "field": "count", "operator": "gt", "value": 100 }
    ],
    "mitre": { "tactic": "Impact", "techniques": ["..."] }
  }
]
```

### `GET /model`

Metadata and evaluation metrics for the currently served run(s) —
everything `nids.training.artifacts.load_run` recorded at training time.
`anomaly_detector` is `null` unless `--anomaly-run-id` was passed.

**Response** (`ModelInfoResponse`)
```json
{
  "run_id": "random_forest_20260115T120000Z",
  "model_name": "random_forest",
  "label_column": "is_attack",
  "metrics": { "accuracy": 0.98, "f1_binary": 0.97, "...": "..." },
  "metadata": { "run_id": "...", "created_at": "...", "git_commit": "...", "...": "..." },
  "anomaly_detector": {
    "run_id": "isolation_forest_20260115T120500Z",
    "model_name": "isolation_forest",
    "metrics": { "accuracy": 0.91, "...": "..." },
    "metadata": { "...": "..." }
  }
}
```

### `GET /mitre`

The full ATT&CK `attack_category` -> tactic/techniques table at once
(`nids.api.mitre.list_all_mappings`) — the same data every prediction's
`mitre` field draws from, but fetchable upfront so a dashboard can render
a reference panel without waiting on a prediction, and without bundling
its own copy of `mitre_attack_mapping.json`. `"normal"` is never a key,
same rule `map_to_mitre` already follows.

**Response** (`dict[str, MitreMappingResponse]`)
```json
{
  "dos": { "tactic": "Impact", "techniques": [{ "id": "T1498", "name": "Network Denial of Service", "url": "https://attack.mitre.org/techniques/T1498/" }] },
  "probe": { "tactic": "Reconnaissance", "techniques": ["..."] },
  "r2l": { "tactic": "Initial Access", "techniques": ["..."] },
  "u2r": { "tactic": "Privilege Escalation", "techniques": ["..."] }
}
```

### `POST /predict`

Score a single raw connection record. `?explain=true` additionally
explains the classifier's verdict (default `false`).

**Request** (`PredictRequest`) — one JSON object with exactly the 41
`nids.data.schema.FEATURE_COLUMNS` fields (numeric columns as numbers,
`protocol_type`/`service`/`flag` as strings). Extra fields are rejected;
missing fields are rejected — both by Pydantic before any ML code runs.

```json
{
  "duration": 0, "protocol_type": "tcp", "service": "http", "flag": "SF",
  "src_bytes": 181, "dst_bytes": 5450, "land": 0, "wrong_fragment": 0,
  "urgent": 0, "hot": 0, "num_failed_logins": 0, "logged_in": 1,
  "...": "... (remaining FEATURE_COLUMNS)"
}
```

**Response** (`PredictResponse`), `POST /predict?explain=true` against an
`attack_category`-trained, hybrid-served run:
```json
{
  "prediction": "dos",
  "probabilities": { "normal": 0.02, "dos": 0.85, "probe": 0.05, "r2l": 0.05, "u2r": 0.03 },
  "confidence": 0.85,
  "attack_category": "dos",
  "anomaly_score": 0.57,
  "is_anomaly": true,
  "severity": "critical",
  "explanation": {
    "base_value": 0.12,
    "top_features": [
      { "feature": "service", "value": "http", "contribution": 0.42, "direction": "positive" },
      { "feature": "src_bytes", "value": 99999, "contribution": 0.31, "direction": "positive" },
      { "feature": "logged_in", "value": 0, "contribution": -0.05, "direction": "negative" }
    ],
    "summary": "Predicted 'dos' primarily due to: service='http' (+0.42), src_bytes=99999 (+0.31), logged_in=0 (-0.05)."
  },
  "risk_score": {
    "score": 87.3,
    "severity": "critical",
    "factors": { "attack_confidence": 0.425, "anomaly": 0.171, "severity_band": 0.2 }
  },
  "mitre": {
    "tactic": "Impact",
    "techniques": [
      { "id": "T1498", "name": "Network Denial of Service", "url": "https://attack.mitre.org/techniques/T1498/" }
    ]
  },
  "alert_id": "3fa1c2e0-...-9b7d"
}
```

| Field | Meaning |
|---|---|
| `prediction` | Whatever label the served classifier was trained on (`is_attack` -> `0`/`1`; `attack_category` -> a category string) |
| `probabilities` | `null` if the served classifier has no `predict_proba` |
| `confidence` | `max(probabilities.values())`, or `null` if `probabilities` is `null` |
| `attack_category` | The prediction itself, only when the served classifier's `label_column == "attack_category"`; otherwise `null` |
| `anomaly_score` | Normalized `0-1`, higher = more anomalous. `null` unless `--anomaly-run-id` is served |
| `is_anomaly` | Whether the anomaly detector flagged this record. `null` unless `--anomaly-run-id` is served |
| `severity` | One of `"critical"`/`"high"`/`"medium"`/`"low"` — see [`nids/api/severity.py`](../src/nids/api/severity.py) for the rule table |
| `explanation` | `null` unless `?explain=true`. Explains the **predicted class** (`prediction` above) — see below |
| `risk_score` | Always present — see [Risk scoring](#risk-scoring) below |
| `mitre` | `null` for `"normal"` predictions, for `is_attack`-only deployments, or for a category absent from the mapping table — see [MITRE ATT&CK mapping](#mitre-attck-mapping) |
| `alert_id` | `null` unless `risk_score.score >= alert_threshold` (default `70`) — populated whether or not a database is configured; only *retrievable later* if one is |

#### Risk scoring

`risk_score.score` (0-100) synthesizes three weighted, `[0,1]`-normalized
components (see [`nids/api/risk.py`](../src/nids/api/risk.py)):
`attack_confidence` (0.5 — the classifier's confidence when it predicted
an attack, `0` for a normal verdict), `anomaly` (0.3 — the anomaly
detector's score, when one is served; its weight is redistributed
proportionally across the other two when it isn't, so a classifier-only
deployment's ceiling is still `100`), and `severity_band` (0.2 — the
existing `severity` folded back in as a coarse anchor). `factors` reports
each component's already-weighted contribution, so
`sum(factors.values()) == score / 100`. `risk_score.severity` is
literally `PredictResponse.severity` — one taxonomy, not two.

#### MITRE ATT&CK mapping

A static, data-driven lookup
([`nids/api/mitre_attack_mapping.json`](../src/nids/api/mitre_attack_mapping.json))
from `attack_category` to a MITRE tactic + techniques. Mapping precision
is capped at category granularity (`dos`/`probe`/`r2l`/`u2r`) — NSL-KDD's
finer per-attack-type label isn't exposed past training. Extending the
mapping (more techniques, a different taxonomy for a different dataset)
is a JSON edit, never a code change.

**`explanation` fields:**

| Field | Meaning |
|---|---|
| `base_value` | The model's baseline output for the explained class, before any feature's contribution |
| `top_features` | Up to 10 raw features (one-hot categorical sub-columns already summed back into their parent, e.g. `service`, never `service_http`), sorted by `\|contribution\|` descending |
| `top_features[].value` | The record's actual raw input value for that feature — not the scaled/encoded transformed value |
| `top_features[].contribution` | Signed SHAP contribution. `base_value + sum(contribution over every raw feature, not just the top 10)` reconstructs the model's own output for the predicted class |
| `top_features[].direction` | `"positive"` pushed toward the predicted class, `"negative"` pushed away |
| `summary` | One deterministic templated sentence naming the top 3 features — not an LLM call |

**Units caveat:** `contribution`/`base_value` are in whichever output space
`shap.TreeExplainer` targets for that model — verified empirically to
differ by model (CatBoost: raw margin/log-odds; scikit-learn
`RandomForestClassifier`: predicted probability; Isolation Forest: its
internal anomaly score). Not necessarily probability-calibrated, but
additive and consistent within one model's own explanations. Don't compare
raw `contribution` magnitudes across differently-typed served models.

### `POST /predict/batch`

Score every row of an uploaded CSV (`multipart/form-data`, field name
`file`), in row order. The CSV must contain all `FEATURE_COLUMNS`; extra
columns are ignored. `?explain=true` explains every row.

**Response** (`BatchPredictResponse`)
```json
{
  "summary": { "total_records": 500, "prediction_counts": { "0": 421, "1": 79 } },
  "results": [
    {
      "prediction": 0, "probabilities": { "0": 0.94, "1": 0.06 }, "confidence": 0.94,
      "attack_category": null, "anomaly_score": 0.12, "is_anomaly": false, "severity": "low",
      "explanation": null,
      "risk_score": { "score": 3.6, "severity": "low", "factors": { "attack_confidence": 0.0, "anomaly": 0.036, "severity_band": 0.02 } },
      "mitre": null, "alert_id": null
    },
    "..."
  ]
}
```

**Batch cost caveats:** `?explain=true` runs SHAP over the whole uploaded
file (vectorized — one `shap_values` call for the batch, not once per
row, but cost still scales with batch size and tree complexity). Risk
scoring and MITRE mapping are cheap pure functions and add negligible
cost regardless of batch size. When `database_url` is configured,
persistence writes one row per prediction (and per raised alert) via
individual synchronous inserts — fine for investigative or moderate
batches; see [`docs/DATABASE.md`](DATABASE.md) for when that stops being
true and what to reach for instead.

## CORS

No `CORSMiddleware` is installed by default — a request from any other
origin (e.g. a dashboard dev server on `localhost:5173`) is blocked by
the browser. This is opt-in and empty-by-default on purpose: the API has
no other origin checking of any kind, so a deployer must name exactly
which origins to trust rather than the server wildcarding for them.
Enable it with a repeatable `--cors-origin` flag:

```bash
python -m nids.api --run-id <run_id> --cors-origin http://localhost:5173
```

`allow_credentials` stays off regardless — the dashboard authenticates
via a `?token=` query parameter (see `/ws/live` below), never cookies, so
there's no session state that needs credentialed CORS.

## Status codes

| Code | When |
|---|---|
| `200` | Successful request |
| `400` | `/predict/batch`: not a `.csv` file, unparseable CSV, or missing required columns. `ValueError` from feature validation maps here. |
| `404` | `/history/*`: no prediction/alert with the given id |
| `413` | `/predict/batch`: uploaded file exceeds `max_upload_size_bytes` (default 10MB) |
| `422` | `/predict`: request body fails Pydantic validation (missing/extra/wrong-type field) — FastAPI's standard validation error shape. `/history/*`: an out-of-range `limit`/`offset` |
| `429` | `/predict`, `/predict/batch`, `/agent/pair`, `/agent/pair/exchange`: rate limit exceeded for this client IP — see [`docs/OBSERVABILITY.md`](OBSERVABILITY.md#rate-limiting) |
| `503` | No model is loaded (should only occur if startup loading failed). `/history/*`: no `database_url` configured for this deployment |

## Example requests

```bash
curl http://localhost:8000/health

curl http://localhost:8000/model

curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"duration": 0, "protocol_type": "tcp", "service": "http", "flag": "SF", "...": "..."}'

curl -X POST 'http://localhost:8000/predict?explain=true' \
  -H "Content-Type: application/json" \
  -d '{"duration": 0, "protocol_type": "tcp", "service": "http", "flag": "SF", "...": "..."}'

curl -X POST http://localhost:8000/predict/batch \
  -F "file=@connections.csv"

curl -X POST 'http://localhost:8000/predict/batch?explain=true' \
  -F "file=@connections.csv"

curl 'http://localhost:8000/history/predictions?severity=critical&limit=10'
curl 'http://localhost:8000/history/alerts?acknowledged=false'
curl -X POST http://localhost:8000/history/alerts/<alert_id>/acknowledge
```

Run the server:

```bash
# classifier only (Milestone 2 behavior)
python -m nids.api --run-id <run_id> --artifact-root models/runs --port 8000

# hybrid: classifier + anomaly detector
python -m nids.api --run-id <run_id> --anomaly-run-id <isolation_forest_run_id> \
  --artifact-root models/runs --port 8000

# with persistence + a custom alert threshold
python -m nids.api --run-id <run_id> --database-url sqlite:///history.db \
  --alert-threshold 60 --artifact-root models/runs --port 8000
```

Training the anomaly detector uses the same training CLI as any other
model, just with `--model isolation_forest` and `--label-column is_attack`
(Isolation Forest has no `attack_category` notion):

```bash
python -m nids.training --model isolation_forest --label-column is_attack
```

## History API

Read access to persisted predictions/alerts (see
[`docs/DATABASE.md`](DATABASE.md)), plus the one write action a SOC
workflow needs. Every route below `503`s unless `--database-url` was
passed at startup.

| Route | Purpose |
|---|---|
| `GET /history/predictions` | List, filtered by `severity`, `attack_category`, `min_risk_score`, `start_date`/`end_date`; paginated by `limit` (default `20`, max `100`) / `offset` |
| `GET /history/predictions/{id}` | Full detail, including `explanation`/`mitre` when present. `404` if unknown |
| `GET /history/alerts` | List, filtered by `level`, `acknowledged`, `start_date`/`end_date`; same pagination shape |
| `GET /history/alerts/{id}` | Full detail. `404` if unknown |
| `POST /history/alerts/{id}/acknowledge` | Flips `acknowledged` to `true`. Idempotent; `404` if unknown. Also records an `alert_acknowledged` audit event — see [`docs/OBSERVABILITY.md`](OBSERVABILITY.md#audit-trail) |
| `GET /history/audit` | List security-action audit events, filtered by `event_type`, `actor`, `start_date`/`end_date`; same pagination shape (Milestone 10) |

List responses share one shape: `{ "items": [...], "total": <int>,
"limit": <int>, "offset": <int> }`. **Pagination** is offset/limit —
simple and sufficient at this scale; cursor-based pagination is the named
upgrade if result sets grow large enough for offset scans to matter.
**Searching** is structured field filters only, not free-text — see
[`docs/DATABASE.md`](DATABASE.md) for why (Elasticsearch is the named
upgrade for that requirement, not adopted now).

## Persistence

Entirely opt-in: unset `database_url` (the default) means zero DB writes
and zero behavior change other than `risk_score`/`mitre`/`alert_id` still
being computed and returned (they always run; only the *write* is
opt-in). Full schema, engine choice, and justification in
[`docs/DATABASE.md`](DATABASE.md).

## Future endpoints

The module split above exists so each of these is additive — a new module
or route, not a restructure of `nids/api`:

- **Isolation Forest anomaly scoring — done (Milestone 3).** Kept here as
  a worked example of the pattern below: `PredictionResult` (in
  `inference.py`) is a dataclass, not a bare dict, so it grew four new
  optional fields without breaking any existing caller, and the anomaly
  detector needed zero new training code (see
  [Training pipeline](../src/nids/training/) and
  `nids/models/anomaly.py`).
- **Further model families.** Any model satisfying the `Classifier`
  protocol (`nids.models.registry`) is a registry entry away from being
  trainable/tunable/servable; one exposing additional signals (like
  `anomaly_score`) is a `hasattr` check away from `inference.py` picking
  it up, exactly as `anomaly_score` was added.
- **SHAP explanations — done (Milestone 4).** `nids/api/explain.py`,
  given the same `ServedEnsemble`, builds a `shap.TreeExplainer` per
  served model (cached by `id()`) and exposes `?explain=true` on the
  existing predict routes. Kept as a worked example of two seams for
  what's next:
  - **Explaining the anomaly detector.** The same `explain_one`/
    `explain_batch` pattern, called against
    `served_ensemble.anomaly_detector` instead of `.classifier` — not
    built, but nothing in the design blocks it.
  - **Non-tree explainer strategies.** `_model_for_shap`/the explainer
    cache in `explain.py` is where a future non-tree model would register
    a different `shap.Explainer` subclass (e.g. `KernelExplainer` with a
    background dataset); `_aggregate_to_raw_features`, `_build_summary`,
    and the schema/route layer are untouched by that addition.
- **Dashboard visualizations — done (Milestone 7).** `frontend/` — a
  React + Vite SPA consuming `/ws/live`, `/history/*`, `/predict*`, and
  `/mitre` exactly as anticipated here: `explanation.top_features`
  (feature/value/contribution/direction) feeds a bar chart with no
  backend redesign, and every prediction's `risk_score`/`mitre`/
  `alert_id` were already shaped for direct display. Full design in
  [`docs/DASHBOARD.md`](DASHBOARD.md).
- **Live packet capture / local monitoring agent — done (Milestone 6).**
  `nids/agent/` (`capture.py`, `sources.py`, `client.py`, `cli.py`) — a
  `python -m nids.agent` process capturing local traffic (or replaying a
  saved `.pcap`) and streaming it to `/agent/ingest`. Exactly the adapter
  pattern anticipated here: the agent produces raw records satisfying
  `FEATURE_COLUMNS` and never runs prediction itself; `source="agent"` on
  every resulting persisted prediction/alert uses the schema slot this
  bullet reserved, with no schema change needed. Full design in
  [`docs/LIVE_MONITORING.md`](LIVE_MONITORING.md).
- **WebSockets / streaming — done (Milestone 6).** `nids/api/ingest.py`
  (`/agent/ingest`, agent -> server) and `nids/api/broadcast.py`
  (`/ws/live`, server -> dashboard), connected by `nids/api/bus.py`'s
  `MessageBus` and `nids/api/worker.py` running the same
  `inference`/`pipeline` orchestration a `/predict` call uses. See
  [`docs/LIVE_MONITORING.md`](LIVE_MONITORING.md).
- **Prediction history / MITRE ATT&CK mapping / Alert engine — done
  (Milestone 5).** `nids/api/store.py` + `history.py`,
  `nids/api/mitre.py`, and `nids/api/alerts.py` respectively. Kept as
  worked examples of the pattern the remaining items below follow.
- **Rate limiting / structured logging / metrics / audit trail — done
  (Milestone 10).** `nids/api/rate_limit.py`, `nids/api/logging_config.py`,
  `nids/api/metrics.py`, and the `audit_events` table in `nids/api/store.py`
  respectively. Full design in [`docs/OBSERVABILITY.md`](OBSERVABILITY.md).
- **Notification integrations (Slack/email) — done (Milestone 12).**
  `nids/api/notifications/{slack,email_channel,dispatcher,publish}.py`
  implement `nids.api.alerts.NotificationChannel` and dispatch
  fire-and-forget (off the request path) whenever `generate_alert`
  returns non-`None` and meets a configurable minimum severity. Teams
  (or any other channel) is the same one-method interface away. Full
  design in [`docs/NOTIFICATIONS.md`](NOTIFICATIONS.md).
- **Threat intelligence feeds.** A future enrichment stage between MITRE
  mapping and alerting (e.g. IP reputation) is another pure function
  consuming `PredictionResult`/the raw record, composed the same way
  `risk.py`/`mitre.py` are today.
- **Rule-based detections — done (Milestone 13).** `nids/api/rules.py`
  produces its own `Alert`s (same dataclass, `source="rule"`) alongside
  the ML-driven path, evaluated purely against the raw record — never
  against a `PredictionResult` — so a rule fires independently of the
  classifier's own verdict. Both can fire for the same record;
  `nids.api.pipeline.finish_record` persists and notifies each
  independently. Full design in [`docs/RULES.md`](RULES.md).
- **Explaining the anomaly detector / non-tree explainer strategies.**
  Unchanged from Milestone 4 — see `nids/api/explain.py`'s module
  docstring.
- **Multi-user auth/RBAC — done (Milestone 11).** Session-token login,
  `analyst`/`admin` roles, `/auth/*` + admin-only `/devices/*`. The audit
  trail's `actor` field (see [`docs/OBSERVABILITY.md`](OBSERVABILITY.md
  #audit-trail)) now records the logged-in username where a route
  requires login, falling back to client IP only where it doesn't
  (`/agent/pair` etc., which stay unauthenticated by design).
- **Cloud deployment (shared Postgres, multiple replicas).** The
  `DATABASE_URL` abstraction (`docs/DATABASE.md`) is exactly this seam —
  swap SQLite for a shared Postgres instance, no application code
  change. Not yet exercised beyond SQLite in practice.
- **Route growth.** `app.py` and `history.py` each build their routes on
  their own `fastapi.APIRouter`, included in `create_app` — `history.py`
  is itself the first real exercise of this pattern (previously only
  documented). Future endpoint groups (`/capture`, `/rules`) follow the
  same shape.

## Tests

`tests/test_api_*.py` mirrors the layering: `test_api_model_loader.py`
(loading, including `ServedEnsemble`), `test_api_inference.py` (pure
prediction, classifier-only and hybrid), `test_api_severity.py`
(table-driven rule tests), `test_api_explain.py` (SHAP shape
normalization, raw-feature aggregation, an additive-consistency check
against each registered model's own output, and end-to-end
`explain_one`/`explain_batch`), `test_api_risk.py` (weighted-component
table tests, weight-renormalization when no anomaly detector is served,
the `sum(factors) == score/100` invariant), `test_api_mitre.py` (every
`ATTACK_CATEGORY` value maps or correctly doesn't), `test_api_alerts.py`
(threshold gating, message composition), `test_api_store.py` (CRUD
round-trips, filters, pagination against a temp SQLite file),
`test_api_history.py` (routes end-to-end, including `503` with no
database and `404` on unknown ids), `test_api_schemas.py`
(request/response contracts), `test_api_app.py` (routes, via
`fastapi.testclient.TestClient`, classifier-only, hybrid, `?explain=true`,
and with/without persistence configured), `test_api_cli.py` (argument
parsing and server wiring, with `uvicorn.run` mocked out).
`tests/test_models_anomaly.py` and
`tests/test_isolation_forest_pipeline_reuse.py` cover the model layer and
prove Isolation Forest needs no new training code.
