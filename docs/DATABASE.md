# Database Decision: SQLite via SQLAlchemy

**Status: Milestone 5, opt-in.** Persistence only activates when
`ServingConfig.database_url` (or `--database-url`) is set — unset, the API
writes nothing and behaves exactly as Milestone 4 left it.

## What we use

- **Engine:** SQLite (Python's standard-library driver, via SQLAlchemy).
- **Access layer:** SQLAlchemy 2.0 (declarative ORM + Core), not raw
  `sqlite3` calls.
- **Schema management:** `Base.metadata.create_all()` at engine creation
  (`nids.api.store.create_db_engine`) — no Alembic migrations wired up yet
  (see [Why not Alembic yet](#why-not-alembic-yet)).
- **Location:** `src/nids/api/store.py` — engine/session setup, the three
  ORM models, and every repository function (`save_*`/`get_*`/`list_*`/
  `acknowledge_alert`).

## Why SQLite

- **Already the platform's pattern.** `nids.training`'s MLflow experiment
  tracking has defaulted to `sqlite:///mlflow.db`
  (`TrainingConfig.tracking_uri`) since Milestone 1. Reusing SQLite for
  prediction/alert history keeps the whole platform's persistence story
  consistent, rather than introducing a second kind of infrastructure for
  a different subsystem.
- **Zero extra infrastructure.** No database server to install, run, or
  configure — matters for a student project, for CI, and for anyone
  cloning the repo and running the API locally in one command.
- **Sufficient at this scale.** A single-process API serving a modest
  volume of predictions is exactly SQLite's sweet spot; nothing about
  Milestone 5's actual requirements needs more.

## Why SQLAlchemy, not raw `sqlite3`

The ORM/Core layer abstracts the SQL dialect. Every query in `store.py` is
written against SQLAlchemy's `select()`/ORM API, not hand-written SQL
strings — so moving to Postgres later (for the multi-user/cloud deployment
this design is explicitly meant not to preclude) is a `DATABASE_URL`
change:

```python
# today
database_url = "sqlite:///history.db"
# later, zero application code changes
database_url = "postgresql://user:pass@host:5432/nids"
```

This is the standard staged-scaling pattern for exactly this situation,
not a novel choice.

## Why not Alembic yet

Alembic (SQLAlchemy's migration tool) is already installed in this
environment, and is the obvious next step — but not yet wired up. There is
no production data to migrate: the schema introduced in this milestone is
brand new, so `create_all()` (create every table if it doesn't exist,
leave existing ones alone) is simple, correct, and sufficient. Standard
practice is to introduce migration tooling *once a real schema exists to
evolve* — adding it before that point is machinery with nothing to do.

**When to introduce it:** the first time a table's shape needs to change
*after* real data has been persisted with the old shape (a new column, a
renamed field, a changed constraint). At that point, `alembic init`
against the models already in `store.py`, generate an initial migration
representing the current schema, and every subsequent schema change
becomes a migration instead of an edit to `create_all()`'s output.

## Why not the alternatives

- **MongoDB / NoSQL.** Tempting given the nested JSON shapes in a
  prediction (`probabilities`, `top_features`, `mitre`), but the History
  API's actual requirements — filter by severity, date range, risk score;
  join an alert back to its prediction — are exactly what relational
  querying is for, and SQL is the more teachable, standard choice for
  this audience. The nested shapes are stored as JSON *columns* within
  the relational schema below (see [Schema](#schema)) — a common,
  pragmatic hybrid, not a reason to adopt a document database wholesale.
- **A time-series database (TimescaleDB, InfluxDB).** Genuinely the right
  tool if the live capture agent (Milestone 6, see
  [`docs/LIVE_MONITORING.md`](LIVE_MONITORING.md)) ever produces
  high-frequency, continuously-arriving write volume that outgrows
  SQLite — named here as the credible next step, not adopted now, since
  actual measured volume hasn't required it yet.
- **Elasticsearch.** The industry-standard choice for full-text search at
  SOC/SIEM scale (the "searching" requirement, at scale, is precisely what
  the ELK stack is for) — named as the natural upgrade *when* structured
  field filtering (severity, category, date range — what the History API
  offers today) is outgrown by a real need for free-text search across
  raw records. Bolting text search onto SQLite now would be solving a
  requirement that doesn't exist yet.
- **A message queue for writes (Celery/Redis) instead of synchronous
  inserts.** A single SQLite insert per prediction is fast enough to do
  inline. FastAPI's `BackgroundTasks`, or a real queue at higher scale, is
  the named upgrade if write latency ever becomes measurable — not
  adopted now.

## Schema

Three tables, `src/nids/api/store.py`:

- **`predictions`** — one row per `/predict`(`/batch`) call when
  persistence is on: id, timestamp, which run(s) served it, the full
  prediction result (prediction, probabilities, confidence,
  attack_category, anomaly_score, is_anomaly, severity, risk_score +
  factors, mitre mapping), the raw input record, and a `source` tag
  (`"api"` for HTTP callers, `"agent"` for the live capture agent —
  Milestone 6, see [`docs/LIVE_MONITORING.md`](LIVE_MONITORING.md) — used
  the schema slot this reserved with no schema change).
- **`explanations`** — one row per prediction *that had `?explain=true`
  used* (a nullable one-to-one relationship, via foreign key) — kept
  separate rather than columns on `predictions` because most rows won't
  have one, exactly mirroring the API's own explanation being opt-in.
- **`alerts`** — one row per prediction that crossed `alert_threshold`:
  level (reuses `predictions.severity`'s taxonomy), title, message, a
  denormalized copy of risk score and MITRE mapping (so an alert is
  fully readable without a join), and `acknowledged` — the one real SOC
  workflow field this milestone adds (an analyst dismisses/acknowledges
  an alert via `POST /history/alerts/{id}/acknowledge`).

Repository functions in `store.py` never return raw ORM instances — every
read returns a plain, already-detached dataclass (`PredictionRecordView`/
`AlertRecordView`), so callers (the History API routes) can't accidentally
touch a closed SQLAlchemy session.

## Reproducing / inspecting the database

```bash
# opt in when starting the API
python -m nids.api --run-id <run_id> --database-url sqlite:///history.db

# inspect directly
sqlite3 history.db ".tables"
sqlite3 history.db "select severity, risk_score, created_at from predictions order by created_at desc limit 5;"
```

No setup step is required beyond passing `--database-url` — the tables are
created automatically on first startup with a given URL.
