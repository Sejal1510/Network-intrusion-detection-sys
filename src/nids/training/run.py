"""The training orchestrator: composes the independent stages (data
loading, feature engineering, model training, evaluation, artifact
persistence, experiment tracking) into one reusable experiment pipeline.

Each stage is implemented elsewhere and unchanged here -- this module only
sequences calls to nids.data, nids.features, nids.models, and the rest of
nids.training. Swapping models is a TrainingConfig change; nothing in this
module is CatBoost-, Random-Forest-, or any-other-model-specific.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from nids.data import load_test, load_train
from nids.features import FeatureEngineer
from nids.models.registry import build_model
from nids.training.artifacts import RunArtifacts, save_run
from nids.training.config import TrainingConfig
from nids.training.evaluate import evaluate_classifier
from nids.training.tracking import log_run


def _default_run_id(config: TrainingConfig) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{config.model_name}_{timestamp}"


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
    # -- Data loading --------------------------------------------------
    if train_df is None:
        train_df = load_train(full=config.train_full)
    if test_df is None:
        test_df = load_test(exclude_difficulty_21=config.test_exclude_difficulty_21)

    # -- Feature engineering --------------------------------------------
    feature_engineer = FeatureEngineer().fit(train_df)
    train_matrix = feature_engineer.transform(train_df)
    test_matrix = feature_engineer.transform(test_df)

    y_train = train_df[config.label_column].to_numpy()
    y_test = test_df[config.label_column].to_numpy()

    # -- Model training ---------------------------------------------------
    model = build_model(config.model_name, random_state=config.random_seed, **config.model_params)
    model.fit(train_matrix.X, y_train)

    # -- Evaluation --------------------------------------------------------
    y_pred = model.predict(test_matrix.X)
    y_proba = model.predict_proba(test_matrix.X) if hasattr(model, "predict_proba") else None
    metrics = evaluate_classifier(y_test, y_pred, y_proba)

    # -- Artifact persistence ----------------------------------------------
    run_id = config.run_name or _default_run_id(config)
    run_artifacts = save_run(config.artifact_root / run_id, model, feature_engineer, config, metrics)

    # -- Experiment tracking -------------------------------------------------
    if log_to_mlflow:
        log_run(run_artifacts)

    return run_artifacts
