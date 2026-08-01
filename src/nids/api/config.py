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
    # MessageBus backend for live monitoring (nids.api.bus): unset means
    # InMemoryBus (default, zero new infrastructure -- one process, no
    # Redis). Set to e.g. "redis://localhost:6379" for RedisBus, the
    # opt-in scaling tier (see docs/LIVE_MONITORING.md).
    redis_url: str | None = None
    # Signs agent pairing tokens (nids.api.agent_auth). Unset means a
    # random key is generated once at startup -- fine since pairing
    # tokens are short-lived and meant to be redeemed within minutes of
    # issuing; already-*paired* devices are unaffected by a restart
    # (their credential is verified by a stored hash, not this key). Set
    # explicitly for a deployment where issued-but-unredeemed pairing
    # tokens must survive a restart.
    secret_key: str | None = None

    @property
    def run_dir(self) -> Path:
        return self.artifact_root / self.run_id
