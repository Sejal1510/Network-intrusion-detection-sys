# Inference API

**Status:** Milestone 4 — explainable hybrid detection. The API serves a
required supervised classifier and an optional unsupervised anomaly
detector (Isolation Forest) together, and can explain any prediction's
classifier verdict with SHAP on request. Live packet capture, alerts, and
history are future milestones — see [Future endpoints](#future-endpoints)
for how they plug into this architecture without restructuring it.

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
   -> response schema -> JSON
```

If no anomaly detector is pinned, `anomaly_score`/`is_anomaly` are `null`
and `severity` is computed from classifier confidence alone — `/predict`
reproduces Milestone 2's behavior exactly. If `explain` is omitted or
`false` (the default), `explanation` is `null` and zero SHAP code runs —
`/predict` reproduces Milestone 3's behavior exactly.
`nids.api.inference` has never imported `shap` and still doesn't;
`nids.api.explain` is a second delegate the route calls *alongside* it,
not a change inside it.

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
| `nids/api/schemas.py` | Pydantic request/response contracts |
| `nids/api/app.py` | FastAPI routes — HTTP boundary only |
| `nids/api/cli.py` | `python -m nids.api --run-id ... [--anomaly-run-id ...]` entrypoint |
| `nids/models/anomaly.py` | `IsolationForestClassifier` — Isolation Forest adapted to the `Classifier` protocol, plus `explainable_model` for SHAP |

## Endpoints

### `GET /health`

Liveness probe. Always returns `200` if the process is up; `model_loaded`
reports whether a served model is available.

**Response** (`HealthResponse`)
```json
{ "status": "ok", "model_loaded": true }
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

**Response** (`PredictResponse`), `POST /predict?explain=true`:
```json
{
  "prediction": 1,
  "probabilities": { "0": 0.06, "1": 0.94 },
  "confidence": 0.94,
  "attack_category": null,
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
    "summary": "Predicted 1 primarily due to: service='http' (+0.42), src_bytes=99999 (+0.31), logged_in=0 (-0.05)."
  }
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
      "explanation": null
    },
    "..."
  ]
}
```

**Batch explanation cost caveat:** unlike prediction, which is cheap per
row, `?explain=true` on `/predict/batch` runs SHAP over the whole uploaded
file (vectorized — one `shap_values` call for the batch, not once per
row, but the cost still scales with batch size and tree complexity).
Recommended for investigative or moderate-sized batches, not
high-throughput bulk scoring.

## Status codes

| Code | When |
|---|---|
| `200` | Successful request |
| `400` | `/predict/batch`: not a `.csv` file, unparseable CSV, or missing required columns. `ValueError` from feature validation maps here. |
| `422` | `/predict`: request body fails Pydantic validation (missing/extra/wrong-type field) — FastAPI's standard validation error shape |
| `503` | No model is loaded (should only occur if startup loading failed) |

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
```

Run the server:

```bash
# classifier only (Milestone 2 behavior)
python -m nids.api --run-id <run_id> --artifact-root models/runs --port 8000

# hybrid: classifier + anomaly detector
python -m nids.api --run-id <run_id> --anomaly-run-id <isolation_forest_run_id> \
  --artifact-root models/runs --port 8000
```

Training the anomaly detector uses the same training CLI as any other
model, just with `--model isolation_forest` and `--label-column is_attack`
(Isolation Forest has no `attack_category` notion):

```bash
python -m nids.training --model isolation_forest --label-column is_attack
```

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
- **Dashboard visualizations.** `explanation.top_features`
  (feature/value/contribution/direction) is already shaped for a bar or
  waterfall chart with no backend redesign; `base_value` plus every raw
  feature's contribution sums to the model's own output, which is exactly
  what a waterfall chart needs.
- **Live packet capture / local monitoring agent.** Per
  `nids.features.contracts`'s adapter pattern, a capture agent is just
  another producer of a DataFrame satisfying `FEATURE_COLUMNS` — it calls
  the same `inference.predict_one`, either in-process as a new module or
  out-of-process by POSTing to `/predict`.
- **WebSockets / streaming.** FastAPI serves WebSocket routes from the same
  app alongside REST routes; a streaming route calls `inference.predict_one`
  per message. No change to `inference.py` or existing routes.
- **Prediction history.** A future `nids/api/store.py` persists
  `PredictResponse` — including `explanation` when `?explain=true` was
  used — as-is; it's already a structured, serializable shape, no schema
  redesign needed.
- **MITRE ATT&CK mapping.** A future enrichment keyed off
  `attack_category` (already a response field) is an additive lookup
  table, unrelated to `explain.py`.
- **Alert engine.** Consumes `severity` (Milestone 3) and
  `explanation.summary`/`top_features` (Milestone 4) as alert message
  content — a new consumer, not a backend change.
- **Route growth.** `app.py` builds its routes on a `fastapi.APIRouter`
  from the start. Future endpoint groups (`/capture`, `/history`,
  `/alerts`) become their own router modules, included via
  `app.include_router(...)` in `create_app`, rather than edits to the
  existing routes.

## Tests

`tests/test_api_*.py` mirrors the layering: `test_api_model_loader.py`
(loading, including `ServedEnsemble`), `test_api_inference.py` (pure
prediction, classifier-only and hybrid), `test_api_severity.py`
(table-driven rule tests), `test_api_explain.py` (SHAP shape
normalization, raw-feature aggregation, an additive-consistency check
against each registered model's own output, and end-to-end
`explain_one`/`explain_batch`), `test_api_schemas.py` (request/response
contracts), `test_api_app.py` (routes, via `fastapi.testclient.TestClient`,
classifier-only, hybrid, and `?explain=true`), `test_api_cli.py` (argument
parsing and server wiring, with `uvicorn.run` mocked out).
`tests/test_models_anomaly.py` and
`tests/test_isolation_forest_pipeline_reuse.py` cover the model layer and
prove Isolation Forest needs no new training code.
