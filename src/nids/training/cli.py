"""Command-line entry point for running a training experiment.

Kept separate from nids.training.run (and out of nids/training/__init__.py's
import graph) so `python -m nids.training` doesn't re-import its own module
as __main__.
"""

from __future__ import annotations

import argparse

from nids.training.config import TrainingConfig
from nids.training.run import run_training


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
    args = parser.parse_args()

    config = TrainingConfig(
        model_name=args.model,
        random_seed=args.seed,
        train_full=not args.quick,
        label_column=args.label_column,
    )

    run_artifacts = run_training(config, log_to_mlflow=not args.no_mlflow)

    print(f"run_id: {run_artifacts.metadata['run_id']}")
    print(f"saved to: {run_artifacts.run_dir}")
    print("metrics:")
    for key in ("accuracy", "precision_binary", "recall_binary", "f1_binary", "roc_auc"):
        if key in run_artifacts.metrics:
            print(f"  {key}: {run_artifacts.metrics[key]:.4f}")

    return 0
