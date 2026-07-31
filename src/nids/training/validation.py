"""K-fold cross-validation: a statistically fairer evaluation protocol than
a single held-out train/test split, for comparing models before committing
to hyperparameter tuning.

This module adds no new feature-engineering, model-training, or evaluation
logic of its own -- it calls `nids.training.core.fit_and_evaluate` once per
fold (see that module for why the fold split, not this one, is what keeps
results leakage-free) and aggregates the per-fold metrics that
`nids.training.evaluate.evaluate_classifier` already computes.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

from nids.data import load_train
from nids.training.config import TrainingConfig
from nids.training.core import fit_and_evaluate
from nids.training.evaluate import scalar_metrics


@dataclass(frozen=True)
class CVResult:
    config: TrainingConfig
    n_folds: int
    fold_metrics: list[dict[str, Any]]
    aggregated_metrics: dict[str, dict[str, float]]


def _aggregate_fold_metrics(fold_metrics: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Mean/std/min/max per scalar metric, computed only over the folds
    where that metric was actually present (e.g. `roc_auc` can be absent
    from a degenerate fold; see evaluate_classifier)."""
    values_by_key: dict[str, list[float]] = defaultdict(list)
    for metrics in fold_metrics:
        for key, value in scalar_metrics(metrics).items():
            values_by_key[key].append(value)

    aggregated: dict[str, dict[str, float]] = {}
    for key, values in values_by_key.items():
        arr = np.asarray(values, dtype=float)
        aggregated[key] = {
            "mean": float(arr.mean()),
            "std": float(arr.std(ddof=0)),
            "min": float(arr.min()),
            "max": float(arr.max()),
            "n_folds": len(values),
        }
    return aggregated


def run_cross_validation(
    config: TrainingConfig,
    df: pd.DataFrame | None = None,
) -> CVResult:
    """Run stratified k-fold cross-validation and return per-fold plus
    aggregated metrics.

    `df` is a dependency-injection point like `run_training`'s `train_df`/
    `test_df`: production callers leave it as None (loads
    `nids.data.load_train(full=config.train_full)`); tests pass a small
    in-memory DataFrame directly.

    Folds are stratified on `config.label_column` and generated with a
    fixed `random_state=config.random_seed`, so the same config always
    produces the same folds -- a prerequisite for comparing two models'
    CV results fairly. Each fold fits its own `FeatureEngineer` and model
    from scratch on that fold's training rows only (via
    `nids.training.core.fit_and_evaluate`); no state is shared across
    folds.
    """
    if df is None:
        df = load_train(full=config.train_full)

    y = df[config.label_column].to_numpy()

    # sklearn's StratifiedKFold only *warns* (doesn't raise) when a class has
    # fewer members than cv_folds, then silently falls back to degraded,
    # non-strict stratification for that class -- exactly the kind of silent
    # statistical unfairness this module exists to prevent. Check explicitly
    # instead of trusting that warning to be noticed.
    class_counts = pd.Series(y).value_counts()
    undersized = class_counts[class_counts < config.cv_folds]
    if not undersized.empty:
        raise ValueError(
            f"Cannot stratify into cv_folds={config.cv_folds} folds on "
            f"label_column={config.label_column!r}: class(es) with fewer members "
            f"than cv_folds: {undersized.to_dict()}. Reduce cv_folds or use more data."
        )

    splitter = StratifiedKFold(
        n_splits=config.cv_folds, shuffle=True, random_state=config.random_seed
    )
    splits = list(splitter.split(df, y))

    fold_metrics: list[dict[str, Any]] = []
    for train_idx, val_idx in splits:
        result = fit_and_evaluate(df.iloc[train_idx], df.iloc[val_idx], config)
        fold_metrics.append(result.metrics)

    return CVResult(
        config=config,
        n_folds=config.cv_folds,
        fold_metrics=fold_metrics,
        aggregated_metrics=_aggregate_fold_metrics(fold_metrics),
    )
