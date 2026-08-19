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


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() not in {"0", "false", "no"}


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
        "--pairing-rate-limit",
        type=int,
        default=_env_int("NIDS_PAIRING_RATE_LIMIT_PER_MINUTE", 20),
        help="max /agent/pair + /agent/pair/exchange requests per minute per client IP "
        "(env: NIDS_PAIRING_RATE_LIMIT_PER_MINUTE)",
    )
    parser.add_argument(
        "--inference-rate-limit",
        type=int,
        default=_env_int("NIDS_INFERENCE_RATE_LIMIT_PER_MINUTE", 120),
        help="max /predict + /predict/batch requests per minute per client IP "
        "(env: NIDS_INFERENCE_RATE_LIMIT_PER_MINUTE)",
    )
    parser.add_argument(
        "--max-upload-size",
        type=int,
        default=_env_int("NIDS_MAX_UPLOAD_SIZE_BYTES", 10_000_000),
        help="largest /predict/batch CSV upload accepted, in bytes, before a 413 "
        "(env: NIDS_MAX_UPLOAD_SIZE_BYTES)",
    )
    parser.add_argument(
        "--session-ttl-seconds",
        type=int,
        default=_env_int("NIDS_SESSION_TTL_SECONDS", 28_800),
        help="how long a login session (POST /auth/login) stays valid, in seconds "
        "(env: NIDS_SESSION_TTL_SECONDS)",
    )
    parser.add_argument(
        "--auth-rate-limit",
        type=int,
        default=_env_int("NIDS_AUTH_RATE_LIMIT_PER_MINUTE", 10),
        help="max POST /auth/login requests per minute per client IP "
        "(env: NIDS_AUTH_RATE_LIMIT_PER_MINUTE)",
    )
    parser.add_argument(
        "--slack-webhook-url",
        default=os.environ.get("NIDS_SLACK_WEBHOOK_URL"),
        help="Slack incoming-webhook URL; omitted means the Slack notification channel "
        "is never configured (env: NIDS_SLACK_WEBHOOK_URL, see docs/NOTIFICATIONS.md)",
    )
    parser.add_argument(
        "--smtp-host",
        default=os.environ.get("NIDS_SMTP_HOST"),
        help="SMTP server for the email notification channel; omitted means the email "
        "channel is never configured (env: NIDS_SMTP_HOST, see docs/NOTIFICATIONS.md)",
    )
    parser.add_argument(
        "--smtp-port", type=int, default=_env_int("NIDS_SMTP_PORT", 587),
        help="SMTP port (env: NIDS_SMTP_PORT)",
    )
    parser.add_argument(
        "--smtp-username", default=os.environ.get("NIDS_SMTP_USERNAME"),
        help="SMTP auth username; omitted means unauthenticated SMTP (env: NIDS_SMTP_USERNAME)",
    )
    parser.add_argument(
        "--smtp-password", default=os.environ.get("NIDS_SMTP_PASSWORD"),
        help="SMTP auth password (env: NIDS_SMTP_PASSWORD)",
    )
    parser.add_argument(
        "--smtp-from", dest="smtp_from_addr", default=os.environ.get("NIDS_SMTP_FROM"),
        help="'From' address for notification emails (env: NIDS_SMTP_FROM)",
    )
    parser.add_argument(
        "--notify-email-to",
        action="append",
        default=[],
        dest="smtp_to_addrs",
        help="send notification emails to this address (repeatable); omitted entirely "
        "falls back to the comma-separated NIDS_SMTP_TO env var. The email channel is "
        "only configured if --smtp-host and at least one recipient are both set.",
    )
    parser.add_argument(
        "--smtp-no-tls",
        action="store_true",
        default=not _env_bool("NIDS_SMTP_USE_TLS", True),
        help="disable STARTTLS for the email channel (env: NIDS_SMTP_USE_TLS=false)",
    )
    parser.add_argument(
        "--notification-min-severity",
        choices=["low", "medium", "high", "critical"],
        default=os.environ.get("NIDS_NOTIFICATION_MIN_SEVERITY", "high"),
        help="minimum Alert severity that actually notifies a configured channel "
        "(env: NIDS_NOTIFICATION_MIN_SEVERITY, see docs/NOTIFICATIONS.md)",
    )
    parser.add_argument(
        "--abuseipdb-api-key",
        default=os.environ.get("NIDS_ABUSEIPDB_API_KEY"),
        help="AbuseIPDB API key; omitted means that IOC enrichment provider is never "
        "configured (env: NIDS_ABUSEIPDB_API_KEY, see docs/THREAT_INTEL.md)",
    )
    parser.add_argument(
        "--greynoise-api-key",
        default=os.environ.get("NIDS_GREYNOISE_API_KEY"),
        help="GreyNoise API key; omitted means that IOC enrichment provider is never "
        "configured (env: NIDS_GREYNOISE_API_KEY, see docs/THREAT_INTEL.md)",
    )
    parser.add_argument(
        "--enrichment-cache-ttl-seconds",
        type=int,
        default=_env_int("NIDS_ENRICHMENT_CACHE_TTL_SECONDS", 86_400),
        help="how long a cached IOC enrichment result is trusted before a re-lookup is "
        "allowed (env: NIDS_ENRICHMENT_CACHE_TTL_SECONDS, default 86400 = 24h)",
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
    smtp_to_addrs = args.smtp_to_addrs or _split_origins(os.environ.get("NIDS_SMTP_TO", ""))

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
        pairing_rate_limit_per_minute=args.pairing_rate_limit,
        inference_rate_limit_per_minute=args.inference_rate_limit,
        max_upload_size_bytes=args.max_upload_size,
        session_ttl_seconds=args.session_ttl_seconds,
        auth_rate_limit_per_minute=args.auth_rate_limit,
        slack_webhook_url=args.slack_webhook_url,
        smtp_host=args.smtp_host,
        smtp_port=args.smtp_port,
        smtp_username=args.smtp_username,
        smtp_password=args.smtp_password,
        smtp_from_addr=args.smtp_from_addr,
        smtp_to_addrs=tuple(smtp_to_addrs),
        smtp_use_tls=not args.smtp_no_tls,
        notification_min_severity=args.notification_min_severity,
        abuseipdb_api_key=args.abuseipdb_api_key,
        greynoise_api_key=args.greynoise_api_key,
        enrichment_cache_ttl_seconds=args.enrichment_cache_ttl_seconds,
    )
    app = create_app(config)

    uvicorn.run(app, host=config.host, port=config.port)
    return 0
