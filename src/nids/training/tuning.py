"""Hyperparameter tuning: reusable, model-agnostic search over
TrainingConfig.model_params, scored via the same cross-validation protocol
used for fair model comparison (see nids.training.validation) -- tuning
picks a winner by CV mean, never by peeking at a single split or the
held-out test set.

The search strategy (see nids.training.search) decides *which* candidates
to try; this module decides *how to score* each one -- identical for every
strategy and every registered model, since it's built on the same
`run_cross_validation` every model already goes through.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

import pandas as pd

from nids.data import load_train
from nids.training.artifacts import default_run_id
from nids.training.config import TrainingConfig
from nids.training.search import SearchStrategy
from nids.training.validation import CVResult, run_cross_validation


@dataclass(frozen=True)
class TuningTrial:
    trial_index: int
    params: dict[str, Any]
    config: TrainingConfig
    cv_result: CVResult
    score: float


@dataclass(frozen=True)
class TuningResult:
    study_run_id: str
    base_config: TrainingConfig
    search_space: dict[str, list[Any]]
    strategy_name: str
    metric: str
    maximize: bool
    trials: list[TuningTrial]
    best_trial: TuningTrial


def _score(cv_result: CVResult, metric: str) -> float:
    if metric not in cv_result.aggregated_metrics:
        raise ValueError(
            f"metric={metric!r} is not among this run's evaluation metrics: "
            f"{sorted(cv_result.aggregated_metrics)}."
        )
    return cv_result.aggregated_metrics[metric]["mean"]


def _select_best(trials: list[TuningTrial], maximize: bool) -> TuningTrial:
    return max(trials, key=lambda t: t.score) if maximize else min(trials, key=lambda t: t.score)


def search_hyperparameters(
    base_config: TrainingConfig,
    search_space: dict[str, list[Any]],
    strategy: SearchStrategy,
    df: pd.DataFrame | None = None,
    metric: str = "accuracy",
    maximize: bool = True,
) -> TuningResult:
    """Score every candidate `strategy` proposes via cross-validation and
    return the full result. Pure computation -- no artifacts saved, nothing
    logged to MLflow (see `run_hyperparameter_search` for that).

    Each candidate is merged into `base_config.model_params` (candidate
    values win on key collision) and evaluated with
    `nids.training.validation.run_cross_validation`, so every trial goes
    through the exact same leakage-free, fresh-FeatureEngineer-per-fold
    protocol as a standalone CV run -- there is no separate, cheaper
    "tuning evaluation" path to keep in sync with the real one.

    `df` is a dependency-injection point like `run_cross_validation`'s:
    production callers leave it as None; tests pass a small in-memory
    DataFrame directly. It's loaded once (if needed) and reused across all
    candidates so every trial sees identical data.
    """
    candidates = strategy.generate_candidates(search_space)
    if not candidates:
        raise ValueError("search_space produced zero candidates to try.")

    if df is None:
        df = load_train(full=base_config.train_full)

    study_run_id = base_config.run_name or default_run_id(base_config.model_name, suffix="tuning")

    trials: list[TuningTrial] = []
    for idx, candidate in enumerate(candidates):
        trial_config = dataclasses.replace(
            base_config,
            model_params={**base_config.model_params, **candidate},
            run_name=f"{study_run_id}_trial{idx:03d}",
        )
        cv_result = run_cross_validation(trial_config, df=df)
        trials.append(
            TuningTrial(
                trial_index=idx,
                params=candidate,
                config=trial_config,
                cv_result=cv_result,
                score=_score(cv_result, metric),
            )
        )

    return TuningResult(
        study_run_id=study_run_id,
        base_config=base_config,
        search_space=search_space,
        strategy_name=type(strategy).__name__,
        metric=metric,
        maximize=maximize,
        trials=trials,
        best_trial=_select_best(trials, maximize),
    )
