"""The training orchestrator: composes the independent stages (data
loading, fit+evaluate, artifact persistence, experiment tracking) into one
reusable experiment pipeline for a single held-out train/test split.

Each stage is implemented elsewhere and unchanged here -- this module only
sequences calls to nids.data and the rest of nids.training. Swapping models
is a TrainingConfig change; nothing in this module is CatBoost-, Random-
Forest-, or any-other-model-specific. See nids.training.validation for the
k-fold cross-validation counterpart, which shares the same fit_and_evaluate
core rather than duplicating it.
"""

from __future__ import annotations

import pandas as pd

from nids.data import load_test, load_train
from nids.training.artifacts import RunArtifacts, default_run_id, save_run
from nids.training.config import TrainingConfig
from nids.training.core import fit_and_evaluate
from nids.training.tracking import log_run


def run_training(
    config: TrainingConfig,
    train_df: pd.DataFrame | None = None,
    test_df: pd.DataFrame | None = None,
    log_to_mlflow: bool = True,
) -> RunArtifacts:
    """Run one end-to-end training experiment and return its artifacts.

    `train_df` / `test_df` are dependency-injection points: production
    callers leave them as None (data loading stage: `nids.data.load_train`/
    `load_test`, driven by `config`); tests pass small in-memory DataFrames
    directly so they never need the full dataset on disk.
    """
    if train_df is None:
        train_df = load_train(full=config.train_full)
    if test_df is None:
        test_df = load_test(exclude_difficulty_21=config.test_exclude_difficulty_21)

    result = fit_and_evaluate(train_df, test_df, config)

    run_id = config.run_name or default_run_id(config.model_name)
    run_artifacts = save_run(
        config.artifact_root / run_id,
        result.model,
        result.feature_engineer,
        config,
        result.metrics,
    )

    if log_to_mlflow:
        log_run(run_artifacts)

    return run_artifacts
