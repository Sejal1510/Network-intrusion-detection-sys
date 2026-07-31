"""Reusable experiment pipeline: config, model registry integration,
evaluation, and artifact persistence for training NIDS classifiers.
"""

from nids.training.config import TrainingConfig
from nids.training.evaluate import evaluate_classifier

__all__ = ["TrainingConfig", "evaluate_classifier"]
