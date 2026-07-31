"""Reusable experiment pipeline: config, model registry integration,
evaluation, and artifact persistence for training NIDS classifiers.
"""

from nids.training.artifacts import RunArtifacts, load_run, save_run
from nids.training.config import TrainingConfig
from nids.training.core import FitEvalResult, fit_and_evaluate
from nids.training.evaluate import evaluate_classifier
from nids.training.run import run_training
from nids.training.tracking import log_run

__all__ = [
    "FitEvalResult",
    "RunArtifacts",
    "TrainingConfig",
    "evaluate_classifier",
    "fit_and_evaluate",
    "load_run",
    "log_run",
    "run_training",
    "save_run",
]
