"""Serving configuration: which trained run this API process serves.

Kept separate from nids.training.config.TrainingConfig -- a serving process
doesn't train, it only names *which already-trained run*
(nids.training.artifacts.load_run) to load at startup. Pinning an explicit
run_id (rather than auto-selecting "latest") makes which model is live an
explicit, reviewable config change, not an accident of directory mtimes.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

from nids.training.config import TrainingConfig

# Shares the training platform's default run-storage location rather than
# hardcoding a second copy of the same path.
DEFAULT_ARTIFACT_ROOT: Path = TrainingConfig().artifact_root


@dataclasses.dataclass(frozen=True)
class ServingConfig:
    run_id: str
    # Optional second run: an anomaly detector (e.g. isolation_forest)
    # served alongside the classifier for hybrid detection (see
    # nids.api.model_loader.ServedEnsemble). Unset means classifier-only
    # serving, identical to Milestone 2's behavior.
    anomaly_run_id: str | None = None
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT
    host: str = "0.0.0.0"
    port: int = 8000
    # Opt-in persistence (nids.api.store): unset means zero DB writes and
    # zero behavior change from Milestone 4. Set to e.g.
    # "sqlite:///history.db" to persist every prediction/alert.
    database_url: str | None = None
    # Minimum RiskScore.score (0-100) that generates an Alert (see
    # nids.api.alerts). Most predictions should not become alerts.
    alert_threshold: float = 70.0
    # MessageBus backend for live monitoring (nids.api.bus) *and* the rate
    # limiter backend (nids.api.rate_limit): unset means InMemoryBus +
    # InMemoryRateLimiter (default, zero new infrastructure -- one
    # process, no Redis). Set to e.g. "redis://localhost:6379" to move
    # both onto RedisBus/RedisRateLimiter, the opt-in scaling tier (see
    # docs/LIVE_MONITORING.md, docs/OBSERVABILITY.md) -- one connection
    # string for both, not a second Redis config field.
    redis_url: str | None = None
    # Signs agent pairing tokens (nids.api.agent_auth). Unset means a
    # random key is generated once at startup -- fine since pairing
    # tokens are short-lived and meant to be redeemed within minutes of
    # issuing; already-*paired* devices are unaffected by a restart
    # (their credential is verified by a stored hash, not this key). Set
    # explicitly for a deployment where issued-but-unredeemed pairing
    # tokens must survive a restart.
    secret_key: str | None = None
    # Origins allowed to make cross-origin requests (e.g. a dashboard
    # dev server on a different port/host). Empty means no CORS
    # middleware at all -- the safest default, since this API otherwise
    # has no origin checking of any kind. Tuple (not list) to keep this
    # dataclass hashable/immutable like every other field here.
    cors_origins: tuple[str, ...] = ()
    # Requests allowed per 60-second window, per client IP, to POST
    # /agent/pair and POST /agent/pair/exchange (nids.api.rate_limit,
    # nids.api.ingest) -- see docs/OBSERVABILITY.md; these routes have no
    # auth (a device isn't credentialed until pairing succeeds), so this
    # is the only abuse control they get. Generous enough that a real
    # pairing handshake (one /pair call, one /pair/exchange call) never
    # trips it.
    pairing_rate_limit_per_minute: int = 20
    # Requests allowed per 60-second window, per client IP, to POST
    # /predict and POST /predict/batch (nids.api.rate_limit, nids.api.app)
    # -- both are public and unauthenticated, and /predict/batch also has
    # no upload size cap of its own (see max_upload_size_bytes), making
    # this its only throttle today. Higher than
    # pairing_rate_limit_per_minute since legitimate usage predicts far
    # more often than it pairs.
    inference_rate_limit_per_minute: int = 120
    # Largest CSV nids.api.app's /predict/batch will read into memory,
    # in bytes, before rejecting the upload with 413. The route otherwise
    # has no size/row cap at all -- 10MB is generous for an investigative
    # batch upload while still bounding worst-case memory use per request.
    max_upload_size_bytes: int = 10_000_000
    # How long a session token issued by POST /auth/login stays valid
    # (nids.api.user_auth, nids.api.auth) before /auth/me and every
    # login-gated route (/history/*, /devices/*) start 401ing it, even if
    # never explicitly logged out. 8 hours -- one working shift; long
    # enough that a SOC analyst isn't repeatedly re-logging-in mid-shift,
    # short enough that a stolen/forgotten token doesn't stay valid
    # indefinitely (unlike a device credential, which has no expiry at
    # all -- see nids.api.agent_auth -- because a paired device is meant
    # to run unattended for weeks).
    session_ttl_seconds: int = 28_800
    # Requests allowed per 60-second window, per client IP, to POST
    # /auth/login (nids.api.rate_limit, nids.api.auth) -- its own budget,
    # not a reuse of pairing_rate_limit_per_minute: that value (20/min) is
    # tuned so a real pairing handshake never trips it, which is far too
    # generous for login -- a legitimate user logs in rarely, so a low
    # limit here is a real brute-force backstop rather than just an abuse
    # backstop.
    auth_rate_limit_per_minute: int = 10
    # Slack "Incoming Webhook" URL (nids.api.notifications.slack) --
    # unset means the Slack channel is never constructed, same
    # "unset = feature off, zero behavior change" convention as
    # database_url/redis_url above.
    slack_webhook_url: str | None = None
    # SMTP server for the email channel (nids.api.notifications.
    # email_channel). All four of host/from_addr/to_addrs (non-empty)
    # must be set for the channel to be constructed -- username/password
    # are optional (an internal relay may allow anonymous send).
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_addr: str | None = None
    smtp_to_addrs: tuple[str, ...] = ()
    smtp_use_tls: bool = True
    # Minimum Alert.level (nids.api.alerts.meets_min_severity) that
    # actually notifies a configured channel. Deliberately separate from
    # alert_threshold: not every alert (SOC-dashboard-worthy) should page
    # someone (human-interruptive) -- "high" by default so a Slack/email
    # channel isn't drowned in "low"/"medium" noise the moment it's
    # configured.
    notification_min_severity: str = "high"
    # API keys for nids.api.threat_intel's IOC enrichment providers.
    # Unset means that provider is never constructed (nids.api.threat_intel.
    # build_providers) -- same "unset = feature off" convention as
    # slack_webhook_url/smtp_* above. Neither set means
    # nids.api.app never starts the enrichment dispatcher task at all.
    abuseipdb_api_key: str | None = None
    greynoise_api_key: str | None = None
    # How long a cached nids.api.store ioc_enrichments row (keyed on
    # indicator+provider) is trusted before a re-lookup is allowed. IP
    # reputation doesn't meaningfully change minute-to-minute, so this
    # defaults generously (24h) -- the point is avoiding repeated external
    # lookups for the same indicator, not real-time freshness.
    enrichment_cache_ttl_seconds: int = 86_400

    @property
    def run_dir(self) -> Path:
        return self.artifact_root / self.run_id
