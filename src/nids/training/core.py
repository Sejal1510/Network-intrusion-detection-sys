"""The shared fit+evaluate primitive.

This is the one place a raw (train_df, eval_df) pair becomes a fitted
FeatureEngineer, a fitted model, and evaluation metrics on the eval split.
Both `nids.training.run` (a single held-out train/test split) and
`nids.training.validation` (k-fold cross-validation) call this same
function per split -- neither reimplements feature fitting, model
training, or evaluation. Adding a third evaluation protocol later means
calling this function again, not copying its body.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from nids.features import FeatureEngineer
from nids.models.registry import Classifier, build_model
from nids.training.config import TrainingConfig
from nids.training.evaluate import evaluate_classifier


@dataclass(frozen=True)
class FitEvalResult:
    feature_engineer: FeatureEngineer
    model: Classifier
    metrics: dict[str, Any]


def fit_and_evaluate(
    train_df: pd.DataFrame,
    eval_df: pd.DataFrame,
    config: TrainingConfig,
) -> FitEvalResult:
    """Fit a FeatureEngineer and a model on `train_df` only, then evaluate
    on `eval_df`.

    `train_df`/`eval_df` may be a fixed train/test split or a single CV
    fold's train/validation partition -- this function doesn't know or
    care which. Fitting the FeatureEngineer on `train_df` alone (never on
    `eval_df`, never on their union) is what keeps this leakage-free: no
    statistic computed from validation/test rows ever influences how
    training rows are scaled/imputed/encoded.
    """
    feature_engineer = FeatureEngineer().fit(train_df)
    train_matrix = feature_engineer.transform(train_df)
    eval_matrix = feature_engineer.transform(eval_df)

    y_train = train_df[config.label_column].to_numpy()
    y_eval = eval_df[config.label_column].to_numpy()

    model = build_model(config.model_name, random_state=config.random_seed, **config.model_params)
    model.fit(train_matrix.X, y_train)

    y_pred = model.predict(eval_matrix.X)
    y_proba = model.predict_proba(eval_matrix.X) if hasattr(model, "predict_proba") else None
    metrics = evaluate_classifier(y_eval, y_pred, y_proba)

    return FitEvalResult(feature_engineer=feature_engineer, model=model, metrics=metrics)
