# Deployment

**Status: Milestone 9, Docker + Docker Compose.** Two services — `backend`
(Dockerfile) and `frontend` (frontend/Dockerfile) — wired by
`docker-compose.yml`. No Postgres or Redis: SQLite-on-a-volume and
`InMemoryBus` are the documented defaults at this scale (docs/DATABASE.md,
`nids.api.bus`), so compose persists what's already there rather than
introducing new infrastructure this milestone doesn't need.

## Prerequisites

- Docker + Docker Compose (`docker compose version`).
- At least one trained run under `models/runs/<run_id>/`, produced on the
  host with `python -m nids.training` (see docs/DATASET.md). The API image
  never trains, only serves — trained runs are bind-mounted read-only, never
  baked into the image.

## Quickstart

```bash
cp .env.example .env
# edit .env: set NIDS_RUN_ID to a directory name under models/runs/,
# and NIDS_SECRET_KEY to `python -c "import secrets; print(secrets.token_urlsafe(32))"`

docker compose up --build
```

- Backend: http://localhost:8000 (`/health`, `/docs`, `/mitre`, ...)
- Frontend: http://localhost:8080

`docker compose ps` should show both services `healthy` within ~15s of
startup. `frontend` depends on `backend` being healthy before it starts
(`depends_on: condition: service_healthy`), so a backend misconfiguration
(e.g. a bad `NIDS_RUN_ID`) fails fast instead of leaving a frontend pointed
at a dead API.

## Environment variables

See `.env.example` for the full list with inline explanations. The two
required ones (`NIDS_RUN_ID`, `NIDS_SECRET_KEY`) have no default in
`docker-compose.yml` — compose refuses to start rather than silently
serving with no model or a throwaway signing key.

`VITE_API_BASE_URL` is a build ARG, not a runtime env var: Vite bakes it
into the JS bundle at build time (`frontend/src/api/client.ts`), so it must
be the URL the *browser* reaches the backend at, not a Docker-network
hostname like `backend`. Changing it requires `docker compose up --build`,
not just a restart.

## Two bugs found during first real `docker compose up` verification

The initial Milestone 9 commit validated everything Docker would *do*
without actually running Docker (clean `pip install .`, a manually served
run, a manual Vite build-arg check) and explicitly flagged that the real
`docker compose up --build` orchestration still needed a local Docker run.
That run turned up two bugs, both now fixed:

1. **Backend crash-looped on the default `.env`.** `docker-compose.yml` set
   `NIDS_ANOMALY_RUN_ID: ${NIDS_ANOMALY_RUN_ID:-}`, which passes an *empty
   string* into the container when the var is unset, not nothing.
   `nids/api/cli.py` read it with `os.environ.get(...)` (`""`, not `None`),
   and `model_loader.py` only skips loading an anomaly detector when
   `anomaly_run_id is not None` — so `""` passed that check and it tried to
   load a model from `models/runs/` with no run_id, i.e.
   `models/runs/model.joblib`, which doesn't exist. Fixed in `cli.py` by
   collapsing an empty env var to `None` at the source
   (`os.environ.get("NIDS_ANOMALY_RUN_ID") or None`).
2. **Frontend reported `unhealthy` despite serving fine.** The healthcheck
   was `wget --spider http://localhost/`. Alpine's `/etc/hosts` resolves
   `localhost` to `::1` first; nginx only listens on `0.0.0.0` (IPv4), so
   wget got `Connection refused` over IPv6 on every check. Fixed by pointing
   the healthcheck at `http://127.0.0.1/` instead.

Both were only reachable by actually running `docker compose up` — neither
showed up in the build-mechanism checks the original commit relied on. If
you're extending this compose file, verify with a real `docker compose up`
locally rather than reasoning about it from the Dockerfiles alone.

## What's intentionally not here yet

- **No image registry / push step.** Images build locally; there's no
  `docker push` or tag-and-publish workflow. Out of scope until there's an
  actual place to deploy to.
- **No TLS termination.** Both services are plain HTTP, meant to sit behind
  a reverse proxy or load balancer in any real deployment, not to be
  exposed directly.
- **No multi-user auth.** Same as the rest of the platform — see
  docs/API.md's "Future endpoints" section.
