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
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT
    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def run_dir(self) -> Path:
        return self.artifact_root / self.run_id
