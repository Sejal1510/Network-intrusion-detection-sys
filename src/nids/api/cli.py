"""Command-line entry point for running the inference API server.

Kept separate from nids.api.app (and out of nids/api/__init__.py's import
graph) so `python -m nids.api` doesn't re-import its own module as
__main__ -- same reasoning as nids.training.cli.

Every flag also has a `NIDS_*` environment variable fallback (used as the
argparse default), so a container can be configured entirely through
`docker-compose.yml`'s `environment:` block -- no wrapper entrypoint
script duplicating this parsing. An explicit flag always wins over the
env var, matching normal CLI precedence.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn

from nids.api.app import create_app
from nids.api.config import DEFAULT_ARTIFACT_ROOT, ServingConfig
from nids.api.logging_config import setup_logging


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    return float(value) if value else default


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


def _split_origins(value: str) -> list[str]:
    return [origin.strip() for origin in value.split(",") if origin.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the NIDS inference API.")
    parser.add_argument(
        "--run-id",
        default=os.environ.get("NIDS_RUN_ID"),
        help="run_id (under --artifact-root) to serve (env: NIDS_RUN_ID)",
    )
    parser.add_argument(
        "--anomaly-run-id",
        default=os.environ.get("NIDS_ANOMALY_RUN_ID") or None,
        help="optional run_id of an anomaly detector (e.g. isolation_forest) to serve "
        "alongside --run-id for hybrid detection (env: NIDS_ANOMALY_RUN_ID)",
    )
    parser.add_argument(
        "--artifact-root",
        default=os.environ.get("NIDS_ARTIFACT_ROOT", str(DEFAULT_ARTIFACT_ROOT)),
        help="directory containing training run outputs (env: NIDS_ARTIFACT_ROOT)",
    )
    parser.add_argument("--host", default=os.environ.get("NIDS_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=_env_int("NIDS_PORT", 8000))
    parser.add_argument(
        "--database-url",
        default=os.environ.get("NIDS_DATABASE_URL"),
        help="optional SQLAlchemy URL (e.g. sqlite:///history.db) to persist every "
        "prediction/alert to; omitted means no persistence (env: NIDS_DATABASE_URL, "
        "see docs/DATABASE.md)",
    )
    parser.add_argument(
        "--alert-threshold",
        type=float,
        default=_env_float("NIDS_ALERT_THRESHOLD", 70.0),
        help="minimum risk score (0-100) that raises an alert (env: NIDS_ALERT_THRESHOLD)",
    )
    parser.add_argument(
        "--cors-origin",
        action="append",
        default=[],
        dest="cors_origins",
        help="allow this origin for cross-origin requests (repeatable); omit entirely "
        "for no CORS (default, safest). Falls back to the comma-separated "
        "NIDS_CORS_ORIGINS env var when no --cors-origin flag is given at all.",
    )
    parser.add_argument(
        "--secret-key",
        default=os.environ.get("NIDS_SECRET_KEY"),
        help="signs agent pairing tokens (nids.api.agent_auth); omitted means a random "
        "key generated at startup -- set explicitly (env: NIDS_SECRET_KEY) so a "
        "container restart doesn't invalidate unredeemed pairing tokens",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("NIDS_LOG_LEVEL", "INFO"),
        help="root logger level, e.g. DEBUG/INFO/WARNING (env: NIDS_LOG_LEVEL)",
    )
    parser.add_argument(
        "--log-format",
        choices=["text", "json"],
        default=os.environ.get("NIDS_LOG_FORMAT", "text"),
        help="'text' (human-readable, default) or 'json' (one object per line, for "
        "log aggregators) (env: NIDS_LOG_FORMAT)",
    )
    args = parser.parse_args()

    if not args.run_id:
        parser.error("--run-id is required (or set the NIDS_RUN_ID environment variable)")

    setup_logging(args.log_level, json_format=(args.log_format == "json"))

    cors_origins = args.cors_origins or _split_origins(os.environ.get("NIDS_CORS_ORIGINS", ""))

    config = ServingConfig(
        run_id=args.run_id,
        anomaly_run_id=args.anomaly_run_id,
        artifact_root=Path(args.artifact_root),
        host=args.host,
        port=args.port,
        database_url=args.database_url,
        alert_threshold=args.alert_threshold,
        cors_origins=tuple(cors_origins),
        secret_key=args.secret_key,
    )
    app = create_app(config)

    uvicorn.run(app, host=config.host, port=config.port)
    return 0
