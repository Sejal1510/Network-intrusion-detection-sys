"""Load the trained model this API process serves, once, at startup.

Thin wrapper around nids.training.artifacts.load_run -- serving reuses the
exact persisted (model, FeatureEngineer, metadata) triple a training run
already produced; there is no separate "export for serving" step or format.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nids.api.config import ServingConfig
from nids.features import FeatureEngineer
from nids.models.registry import Classifier
from nids.training.artifacts import load_run


@dataclass(frozen=True)
class ServedModel:
    run_id: str
    model: Classifier
    feature_engineer: FeatureEngineer
    metadata: dict[str, Any]


def load_served_model(config: ServingConfig) -> ServedModel:
    """Load the run pinned by `config` into memory for serving.

    Raises FileNotFoundError (via load_run) if `config.run_dir` doesn't
    exist -- callers (e.g. app startup) should let that fail loudly rather
    than starting a server with no model loaded.
    """
    run_artifacts = load_run(config.run_dir)
    return ServedModel(
        run_id=config.run_id,
        model=run_artifacts.model,
        feature_engineer=run_artifacts.feature_engineer,
        metadata=run_artifacts.metadata,
    )
