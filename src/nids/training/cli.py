"""Command-line entry point for running a training experiment.

Kept separate from nids.training.run (and out of nids/training/__init__.py's
import graph) so `python -m nids.training` doesn't re-import its own module
as __main__.
"""

from __future__ import annotations

import argparse
from typing import Any

from nids.training.config import TrainingConfig
from nids.training.run import run_training
from nids.training.search import GridSearch, RandomSearch
from nids.training.tuning import run_hyperparameter_search
from nids.training.validation import run_cv_training

# Small, illustrative search spaces -- Version 2 optimizes for clean,
# reproducible tuning infrastructure, not for searching enormous spaces.
DEFAULT_SEARCH_SPACES: dict[str, dict[str, list[Any]]] = {
    "catboost": {
        "iterations": [100, 300],
        "depth": [4, 6, 8],
        "learning_rate": [0.03, 0.1],
    },
    "random_forest": {
        "n_estimators": [100, 300],
        "max_depth": [None, 10, 20],
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a NIDS training experiment.")
    parser.add_argument("--model", default="catboost", help="registered model name")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="train on the 20%% train subsample instead of the full set",
    )
    parser.add_argument(
        "--label-column", default="is_attack", choices=["is_attack", "attack_category"]
    )
    parser.add_argument("--no-mlflow", action="store_true", help="skip MLflow logging")
    parser.add_argument(
        "--cv",
        action="store_true",
        help="run stratified k-fold cross-validation instead of a single train/test split",
    )
    parser.add_argument("--cv-folds", type=int, default=5, help="number of folds when --cv is set")
    parser.add_argument(
        "--tune",
        action="store_true",
        help="run hyperparameter search (via cross-validation) instead of a single split",
    )
    parser.add_argument(
        "--search-strategy",
        default="grid",
        choices=["grid", "random"],
        help="candidate-generation strategy when --tune is set",
    )
    parser.add_argument(
        "--n-iter", type=int, default=10, help="candidates to sample when --search-strategy=random"
    )
    parser.add_argument("--metric", default="accuracy", help="metric to select the best trial by")
    parser.add_argument(
        "--minimize", action="store_true", help="select the trial with the lowest --metric"
    )
    args = parser.parse_args()

    config = TrainingConfig(
        model_name=args.model,
        random_seed=args.seed,
        train_full=not args.quick,
        label_column=args.label_column,
        cv_folds=args.cv_folds,
    )

    if args.tune:
        if args.model not in DEFAULT_SEARCH_SPACES:
            raise SystemExit(
                f"No default search space registered for model {args.model!r}. "
                f"Known: {sorted(DEFAULT_SEARCH_SPACES)}."
            )
        strategy = (
            GridSearch()
            if args.search_strategy == "grid"
            else RandomSearch(n_iter=args.n_iter, random_state=args.seed)
        )
        tuning_artifacts = run_hyperparameter_search(
            config,
            DEFAULT_SEARCH_SPACES[args.model],
            strategy,
            metric=args.metric,
            maximize=not args.minimize,
            log_to_mlflow=not args.no_mlflow,
        )
        print(f"run_id: {tuning_artifacts.metadata['run_id']}")
        print(f"saved to: {tuning_artifacts.run_dir}")
        print(f"{tuning_artifacts.metadata['n_trials']} trials, best by {args.metric}:")
        print(f"  params: {tuning_artifacts.metadata['best_params']}")
        print(f"  score: {tuning_artifacts.metadata['best_score']:.4f}")
        print(f"  trial run_id: {tuning_artifacts.metadata['best_trial_run_id']}")
        return 0

    if args.cv:
        cv_artifacts = run_cv_training(config, log_to_mlflow=not args.no_mlflow)
        print(f"run_id: {cv_artifacts.metadata['run_id']}")
        print(f"saved to: {cv_artifacts.run_dir}")
        print(f"aggregated metrics over {cv_artifacts.n_folds} folds:")
        for key in ("accuracy", "precision_binary", "recall_binary", "f1_binary", "roc_auc"):
            if key in cv_artifacts.aggregated_metrics:
                stats = cv_artifacts.aggregated_metrics[key]
                print(f"  {key}: {stats['mean']:.4f} +/- {stats['std']:.4f}")
        return 0

    run_artifacts = run_training(config, log_to_mlflow=not args.no_mlflow)

    print(f"run_id: {run_artifacts.metadata['run_id']}")
    print(f"saved to: {run_artifacts.run_dir}")
    print("metrics:")
    for key in ("accuracy", "precision_binary", "recall_binary", "f1_binary", "roc_auc"):
        if key in run_artifacts.metrics:
            print(f"  {key}: {run_artifacts.metrics[key]:.4f}")

    return 0
