"""Reusable experiment pipeline: config, model registry integration,
evaluation, and artifact persistence for training NIDS classifiers.
"""

from nids.training.artifacts import RunArtifacts, load_run, save_run
from nids.training.config import TrainingConfig
from nids.training.evaluate import evaluate_classifier

__all__ = [
    "RunArtifacts",
    "TrainingConfig",
    "evaluate_classifier",
    "load_run",
    "save_run",
]
