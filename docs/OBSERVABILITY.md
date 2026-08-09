# Production Hardening: Rate Limiting, Logging, Metrics, Audit Trail

**Status: Milestone 10.** Closes the highest-leverage gap left after nine
milestones of feature work: this platform had zero rate limiting, zero
structured logging, zero metrics, and zero audit trail anywhere —
self-documented, not a guess. `docs/DASHBOARD.md` has flagged
`POST /agent/pair`/`/agent/pair/exchange` as having "no rate limit or
auth" since Milestone 7, and `/predict/batch` accepted an arbitrary-size
CSV upload with no cap at all. This milestone closes both, plus adds the
observability a production deployment needs regardless (logging, metrics)
and a security-action audit trail.

## Rate limiting

`src/nids/api/rate_limit.py` — the same "swap the backend without
changing the interface" pattern `nids.api.store`/`nids.api.bus` already
use for `database_url`/`redis_url`:

- `InMemoryRateLimiter` (default, `redis_url` unset): dict-backed
  **fixed-window** counters, scoped to one process.
- `RedisRateLimiter` (opt-in, `redis_url` set): `INCR`+`EXPIRE` per
  `(key, window)` Redis key, shared across every process behind a load
  balancer. Reuses `ServingConfig.redis_url` — the same connection string
  `nids.api.bus` already uses for the message bus — rather than a second
  Redis config field; a deployment that scales to multiple processes
  needs Redis for both at once, not one or the other.

**Fixed window, not sliding window or token bucket**: increment a counter
per `(key, window)`, reset on window rollover. The simplest algorithm
that's still a real bound — exactly `limit` requests per `window_seconds`,
per key, forever. Its one known imprecision (up to ~2x burst at a window
boundary) is an accepted tradeoff: these are abuse backstops for two
specific, named gaps, not a billing-grade throughput guarantee.

Two scopes, each keyed by client IP (`request.client.host`), each its own
`ServingConfig` field / `NIDS_*` env var / CLI flag:

| Scope | Routes | Default | Config |
|---|---|---|---|
| `pairing` | `POST /agent/pair`, `POST /agent/pair/exchange` | 20/min | `pairing_rate_limit_per_minute`, `--pairing-rate-limit`, `NIDS_PAIRING_RATE_LIMIT_PER_MINUTE` |
| `inference` | `POST /predict`, `POST /predict/batch` | 120/min | `inference_rate_limit_per_minute`, `--inference-rate-limit`, `NIDS_INFERENCE_RATE_LIMIT_PER_MINUTE` |

A rejection returns `429` and logs a `logger.warning(...)` line —
**rejections are never written to the audit trail** (see below), so a
sustained abuse attempt can't grow that table unbounded; the structured
log is where that signal belongs.

`/predict/batch` also gained a `max_upload_size_bytes` cap (default
10MB, `--max-upload-size`/`NIDS_MAX_UPLOAD_SIZE_BYTES`) — checked against
the `Content-Length` header up front when present, and against the actual
read size as a fallback, returning `413` over the limit. It previously had
no size/row cap at all.

## Structured logging

`src/nids/api/logging_config.py` — `setup_logging(level, json_format)`,
called once from `nids.api.cli.main` before `create_app` builds anything,
so every existing `logging.getLogger(__name__)` call already in the
codebase (`nids.api.worker`, `nids.agent.client`, `nids.agent.capture`)
picks up the configured handler/formatter via normal logger propagation —
zero changes to those modules. `--log-level`/`NIDS_LOG_LEVEL` (default
`INFO`) and `--log-format`/`NIDS_LOG_FORMAT` (`text`, default, or `json`).

Process-global config (Python's `logging` module is a process-wide
singleton regardless of how many `ServingConfig`s exist), so it's CLI-only
— not a `ServingConfig` field, keeping every test that builds
`create_app(config)` directly unaffected.

`RequestLoggingMiddleware` logs one line per request: method, path,
status, duration in ms, client IP. Sample output:

```
# text (default)
2026-08-05T10:07:41+0000 INFO nids.api.request: POST /agent/pair -> 200 (2.1ms) client=172.18.0.1

# json (NIDS_LOG_FORMAT=json)
{"timestamp": "2026-08-05T10:07:41+0000", "level": "INFO", "logger": "nids.api.request", "message": "POST /agent/pair -> 200 (2.1ms) client=172.18.0.1"}
```

## Metrics

New dependency: `prometheus-client`. `src/nids/api/metrics.py` builds a
**fresh `CollectorRegistry` per `create_app()` call**, not the library's
process-wide default registry — required because the test suite (and any
process serving more than one app instance) calls `create_app()` more
than once; the default registry raises on duplicate metric registration.

`GET /metrics` (unauthenticated, matching `/health`) exposes:

| Metric | Type | Labels | What |
|---|---|---|---|
| `nids_http_requests_total` | Counter | `method`, `route`, `status` | Every HTTP request, by route *template* (e.g. `/history/predictions/{prediction_id}`, not the resolved path — bounded cardinality) |
| `nids_http_request_duration_seconds` | Histogram | `method`, `route`, `status` | Request latency |
| `nids_prediction_duration_seconds` | Histogram | `route` | Prediction latency — **see caveat below** |
| `nids_alerts_raised_total` | Counter | `source` (`api`/`agent`/`rule`) | Every `Alert` actually generated, incremented once per alert (see below) |
| `nids_notifications_sent_total` | Counter | `channel`, `status` (`success`/`failure`) | Every notification channel send attempt (Milestone 12) |

**Caveat: `nids_prediction_duration_seconds`'s two `route` labels aren't
apples-to-apples.** `route="/predict/batch"` wraps exactly
`nids.api.inference.predict_batch` — pure inference. `route="/predict"`
wraps the whole per-record pipeline (`nids.api.pipeline.process_record`),
because `/predict` has no inference-only call site in `app.py` to isolate
without either instrumenting `pipeline.py` itself or duplicating
orchestration logic in the route. Documented here and in the metric's
own `HELP` text rather than hidden.

**`nids_alerts_raised_total`'s `source` label lives inside
`nids.api.pipeline.finish_record`, not at the route level (unlike every
other metric here).** Milestone 10 originally incremented it at each
call site (`app.py`/`worker.py`) with a hardcoded `"api"`/`"agent"`
label — correct until Milestone 13 added rule-based detection, at which
point it silently undercounted: a rule-sourced alert alongside an ML one
was never counted at all, because the route only sees
`PredictResponse.alert_id` (one id, naming only the higher-severity
alert), not the full list `finish_record` actually generated. Fixed in
Milestone 14, discovered by the Metrics dashboard page itself (see
below) — its "alerts by source" chart could never show a "rule" bar
until this moved. Now `finish_record` increments once per `Alert` it
actually produces, labeled with that alert's own `.source`, since only
it knows the true count and each one's real source.

Point a local Prometheus at it:

```yaml
scrape_configs:
  - job_name: nids
    static_configs:
      - targets: ["localhost:8000"]
```

## Audit trail

New `audit_events` table (`src/nids/api/store.py`), sibling to
`predictions`/`explanations`/`alerts`/`devices` — see
[`docs/DATABASE.md`](DATABASE.md#schema) for the schema. `GET
/history/audit` (same `503`-without-database / pagination / filter
pattern as `/history/alerts`) reads it back, filterable by `event_type`,
`actor`, `start_date`/`end_date`.

Three `event_type`s today, each written at the route layer right after
the underlying action succeeds (or fails):

| `event_type` | Where | `target_id` | `detail` |
|---|---|---|---|
| `alert_acknowledged` | `POST /history/alerts/{id}/acknowledge` | the alert id | — |
| `device_paired` | `POST /agent/pair/exchange` (success) | the new device id | — |
| `device_pair_failed` | `POST /agent/pair/exchange` (bad/expired token) | — | the error message |

`actor` is the client IP address. **This is an accepted limitation, not
an oversight**: there is no real user auth anywhere in this backend today
— `/history/*` and `/predict` are completely unauthenticated (see
[`docs/API.md`](API.md), [`docs/DASHBOARD.md`](DASHBOARD.md)'s "Auth
model") — so IP is the only identity this system can honestly record. A
future per-user auth layer (see `docs/API.md`'s "Future endpoints" —
"Multi-user deployments") replaces this column's *meaning*, not its
shape: `record_audit_event`'s `actor` parameter is already just a string.

`acknowledge_alert` is idempotent (re-acknowledging a already-acknowledged
alert is a no-op that still returns `200`) — the audit trail records a
row on *every* successful call, including repeats, making `audit_events`
a call log rather than a state-transition log. That's a deliberate choice
for a security audit trail: a repeat acknowledgement attempt is itself a
signal worth keeping (who touched this alert, and when), not noise to
filter out.

## What's intentionally not here yet

- **Dashboard surfacing — done (Milestone 14).** An Audit Log page
  (`GET /history/audit`) and a Metrics page (`GET /metrics/summary`, a
  JSON-friendly read of the same counters `/metrics` exposes in
  Prometheus text format) — both login-gated, any authenticated user,
  same "API first, dashboard later" sequencing Milestone 5 used before
  Milestone 7 existed. Full design in [`docs/DASHBOARD.md`](DASHBOARD.md).
- **No per-user rate limits.** Rate limiting is still per client IP —
  unlike the audit trail's `actor` field (which does record the
  logged-in username where a route requires one, since Milestone 11),
  rate-limit keys were never revisited to use identity instead of IP.
- **No log shipping / centralized log aggregation.** `NIDS_LOG_FORMAT=json`
  makes the output ready to ship (e.g. to a log aggregator's stdout
  collector in a container platform), but no shipper is configured here —
  that's deployment-environment-specific, not something this repo can
  own.
- **No alerting on the metrics themselves** (e.g. a Prometheus alert rule
  for a spike in `429`s). `/metrics` is exposed; wiring an actual
  Alertmanager rule is a deployment-environment concern, same reasoning
  as log shipping above.
