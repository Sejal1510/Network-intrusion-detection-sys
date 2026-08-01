# Inference API

**Status:** Milestone 2, inference only. Live packet capture, SHAP
explanations, alerts, and history are future milestones — see
[Future endpoints](#future-endpoints) for how they plug into this
architecture without restructuring it.

## Architecture

The API serves exactly one trained run (see
[Training pipeline](../src/nids/training/)) as a prediction service. It adds
no new persistence format, feature logic, or model logic — it is a thin HTTP
adapter over the existing training platform.

```
Client (JSON / CSV upload)
   -> FastAPI route (nids/api/app.py)        HTTP concerns only:
                                              parse, validate, format, status codes
   -> Pydantic schema (nids/api/schemas.py)   request shape validation
   -> DataFrame of raw records
   -> nids.api.inference.predict_one/batch    pure, model-agnostic
        -> FeatureEngineer.transform()        REUSED from nids.features
        -> Classifier.predict/predict_proba   REUSED, any registered model
   -> response schema -> JSON
```

The model is loaded **once, at process startup**, via
`nids.training.artifacts.load_run` — the exact `(model, FeatureEngineer,
metrics, metadata)` a training run already produced. Which run is served is
a pinned `run_id` in `ServingConfig` (`nids/api/config.py`), not an
auto-selected "latest" run: promoting a new model to serve is an explicit,
reviewable config change.

| Module | Responsibility |
|---|---|
| `nids/api/config.py` | `ServingConfig` — which run_id to serve, and where |
| `nids/api/model_loader.py` | Load that run into memory once (`ServedModel`) |
| `nids/api/inference.py` | Pure `predict_one`/`predict_batch` — no HTTP awareness |
| `nids/api/schemas.py` | Pydantic request/response contracts |
| `nids/api/app.py` | FastAPI routes — HTTP boundary only |
| `nids/api/cli.py` | `python -m nids.api --run-id ...` entrypoint |

## Endpoints

### `GET /health`

Liveness probe. Always returns `200` if the process is up; `model_loaded`
reports whether a served model is available.

**Response** (`HealthResponse`)
```json
{ "status": "ok", "model_loaded": true }
```

### `GET /model`

Metadata and evaluation metrics for the currently served run — everything
`nids.training.artifacts.load_run` recorded at training time.

**Response** (`ModelInfoResponse`)
```json
{
  "run_id": "random_forest_20260115T120000Z",
  "model_name": "random_forest",
  "label_column": "is_attack",
  "metrics": { "accuracy": 0.98, "f1_binary": 0.97, "...": "..." },
  "metadata": { "run_id": "...", "created_at": "...", "git_commit": "...", "...": "..." }
}
```

### `POST /predict`

Score a single raw connection record.

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

**Response** (`PredictResponse`)
```json
{ "prediction": 0, "probabilities": { "0": 0.94, "1": 0.06 } }
```

`prediction` is whatever label the served model was trained on (`is_attack`
-> `0`/`1`; `attack_category` -> a category string). `probabilities` is
`null` if the served model has no `predict_proba`.

### `POST /predict/batch`

Score every row of an uploaded CSV (`multipart/form-data`, field name
`file`), in row order. The CSV must contain all `FEATURE_COLUMNS`; extra
columns are ignored.

**Response** (`BatchPredictResponse`)
```json
{
  "summary": { "total_records": 500, "prediction_counts": { "0": 421, "1": 79 } },
  "results": [ { "prediction": 0, "probabilities": { "0": 0.94, "1": 0.06 } }, "..." ]
}
```

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

curl -X POST http://localhost:8000/predict/batch \
  -F "file=@connections.csv"
```

Run the server:

```bash
python -m nids.api --run-id <run_id> --artifact-root models/runs --port 8000
```

## Future endpoints

The module split above exists so each of these is additive — a new module
or route, not a restructure of `nids/api`:

- **New model families (e.g. Isolation Forest anomaly scoring).**
  `PredictionResult` (in `inference.py`) is a dataclass, not a bare dict —
  new optional fields (an anomaly score alongside attack/normal
  probability) extend it without breaking existing callers. A model without
  `predict_proba` is already handled (`probabilities` -> `null`).
- **SHAP explanations.** A future `nids/api/explain.py`, given the same
  `ServedModel`, builds a SHAP explainer and exposes `POST
  /predict/explain`. It reuses `inference.py`'s feature-transform step and
  never touches `predict_one`/`predict_batch`.
- **Live packet capture / local monitoring agent.** Per
  `nids.features.contracts`'s adapter pattern, a capture agent is just
  another producer of a DataFrame satisfying `FEATURE_COLUMNS` — it calls
  the same `inference.predict_one`, either in-process as a new module or
  out-of-process by POSTing to `/predict`.
- **WebSockets / streaming.** FastAPI serves WebSocket routes from the same
  app alongside REST routes; a streaming route calls `inference.predict_one`
  per message. No change to `inference.py` or existing routes.
- **Alerts / history.** A persistence concern (a future
  `nids/api/store.py`) that a route calls *after* `inference.py` returns a
  `PredictionResult` — inference itself stays storage-agnostic.
- **Route growth.** `app.py` builds its routes on a `fastapi.APIRouter`
  from the start. Future endpoint groups (`/explain`, `/capture`,
  `/history`, `/alerts`) become their own router modules, included via
  `app.include_router(...)` in `create_app`, rather than edits to the
  existing routes.

## Tests

`tests/test_api_*.py` mirrors the layering: `test_api_model_loader.py`
(loading), `test_api_inference.py` (pure prediction), `test_api_schemas.py`
(request/response contracts), `test_api_app.py` (routes, via
`fastapi.testclient.TestClient`), `test_api_cli.py` (argument parsing and
server wiring, with `uvicorn.run` mocked out).
