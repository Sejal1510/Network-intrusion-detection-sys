"""Reusable experiment pipeline: config, model registry integration,
evaluation, and artifact persistence for training NIDS classifiers.
"""

from nids.training.artifacts import (
    CVRunArtifacts,
    RunArtifacts,
    default_run_id,
    load_cv_run,
    load_run,
    save_cv_run,
    save_run,
)
from nids.training.config import TrainingConfig
from nids.training.core import FitEvalResult, fit_and_evaluate
from nids.training.evaluate import evaluate_classifier
from nids.training.run import run_training
from nids.training.tracking import log_cv_run, log_run
from nids.training.validation import CVResult, run_cross_validation, run_cv_training

__all__ = [
    "CVResult",
    "CVRunArtifacts",
    "FitEvalResult",
    "RunArtifacts",
    "TrainingConfig",
    "default_run_id",
    "evaluate_classifier",
    "fit_and_evaluate",
    "load_cv_run",
    "load_run",
    "log_cv_run",
    "log_run",
    "run_cross_validation",
    "run_cv_training",
    "run_training",
    "save_cv_run",
    "save_run",
]
