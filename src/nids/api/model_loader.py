"""Load the trained model(s) this API process serves, once, at startup.

Thin wrapper around nids.training.artifacts.load_run -- serving reuses the
exact persisted (model, FeatureEngineer, metrics, metadata) a training run
already produced; there is no separate "export for serving" step or format.
"""

from __future__ import annotations

import dataclasses
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
    metrics: dict[str, Any]
    metadata: dict[str, Any]


def load_served_model(config: ServingConfig) -> ServedModel:
    """Load the run pinned by `config.run_id` into memory for serving.

    Raises FileNotFoundError (via load_run) if `config.run_dir` doesn't
    exist -- callers (e.g. app startup) should let that fail loudly rather
    than starting a server with no model loaded.
    """
    run_artifacts = load_run(config.run_dir)
    return ServedModel(
        run_id=config.run_id,
        model=run_artifacts.model,
        feature_engineer=run_artifacts.feature_engineer,
        metrics=run_artifacts.metrics,
        metadata=run_artifacts.metadata,
    )


@dataclass(frozen=True)
class ServedEnsemble:
    """Everything a request needs to produce a hybrid prediction: a
    required classifier and an optional anomaly detector, each its own
    independently trained run (own model, own fitted FeatureEngineer)."""

    classifier: ServedModel
    anomaly_detector: ServedModel | None


def load_served_ensemble(config: ServingConfig) -> ServedEnsemble:
    """Load the classifier run pinned by `config.run_id`, plus the
    optional anomaly-detector run pinned by `config.anomaly_run_id` (both
    under `config.artifact_root`), for hybrid serving.

    The anomaly detector is loaded via the same `load_served_model` path
    as the classifier -- it is just another run, not a different kind of
    artifact. `anomaly_run_id=None` (Milestone 2's default) loads a
    classifier-only ensemble.
    """
    classifier = load_served_model(config)

    anomaly_detector: ServedModel | None = None
    if config.anomaly_run_id is not None:
        anomaly_config = dataclasses.replace(config, run_id=config.anomaly_run_id)
        anomaly_detector = load_served_model(anomaly_config)

    return ServedEnsemble(classifier=classifier, anomaly_detector=anomaly_detector)
