"""Reusable experiment pipeline: config, model registry integration,
evaluation, and artifact persistence for training NIDS classifiers.
"""

from nids.training.artifacts import (
    CVRunArtifacts,
    RunArtifacts,
    TuningRunArtifacts,
    default_run_id,
    load_cv_run,
    load_run,
    load_tuning_run,
    save_cv_run,
    save_run,
    save_tuning_run,
)
from nids.training.config import TrainingConfig
from nids.training.core import FitEvalResult, fit_and_evaluate
from nids.training.evaluate import evaluate_classifier
from nids.training.run import run_training
from nids.training.search import GridSearch, RandomSearch, SearchStrategy
from nids.training.tracking import log_cv_run, log_run, log_tuning_run
from nids.training.tuning import (
    TuningResult,
    TuningTrial,
    run_hyperparameter_search,
    search_hyperparameters,
)
from nids.training.validation import CVResult, run_cross_validation, run_cv_training

__all__ = [
    "CVResult",
    "CVRunArtifacts",
    "FitEvalResult",
    "GridSearch",
    "RandomSearch",
    "RunArtifacts",
    "SearchStrategy",
    "TrainingConfig",
    "TuningResult",
    "TuningRunArtifacts",
    "TuningTrial",
    "default_run_id",
    "evaluate_classifier",
    "fit_and_evaluate",
    "load_cv_run",
    "load_run",
    "load_tuning_run",
    "log_cv_run",
    "log_run",
    "log_tuning_run",
    "run_cross_validation",
    "run_cv_training",
    "run_hyperparameter_search",
    "run_training",
    "save_cv_run",
    "save_run",
    "save_tuning_run",
    "search_hyperparameters",
]
