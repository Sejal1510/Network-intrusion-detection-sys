"""Command-line entry point for the offline adversarial-robustness
evaluator (Milestone 17).

Loads an already-trained run, attacks its true positives on the real NSL-
KDD test split with bounded random-search perturbations, and prints/writes
a JSON report. Never touches nids.api, a live server, or production
inference/thresholds -- this is an offline research tool run against the
project's own model and data, nothing else.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nids.data import load_test, load_train
from nids.evaluation.attack import run_attack
from nids.evaluation.perturbation import FeatureBounds
from nids.evaluation.report import (
    category_breakdown,
    evasion_summary,
    feature_association,
    shap_overlap,
)
from nids.training.artifacts import load_run
from nids.training.config import TrainingConfig

DEFAULT_ARTIFACT_ROOT: Path = TrainingConfig().artifact_root


def _parse_budgets(raw: str) -> list[float]:
    return [float(part) for part in raw.split(",")]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Offline adversarial-robustness evaluation against an already-trained NIDS run."
    )
    parser.add_argument("--run-id", required=True, help="trained run_id under --artifact-root")
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument(
        "--budgets",
        default="0.05,0.15,0.30",
        help="comma-separated perturbation budgets (epsilon), e.g. 0.05,0.15,0.30",
    )
    parser.add_argument(
        "--n-trials", type=int, default=200, help="random-search candidates per row, per budget"
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--test-file",
        choices=["full", "difficulty-21"],
        default="full",
        help="KDDTest+.txt (full) or KDDTest-21.txt (harder, difficulty-21-excluded)",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="attack at most this many true-positive rows (deterministic random sample) -- for a fast smoke run",
    )
    parser.add_argument("--top-n-shap", type=int, default=5)
    parser.add_argument("--output", type=Path, default=None, help="write the full JSON report here")
    args = parser.parse_args()

    run_artifacts = load_run(args.artifact_root / args.run_id)
    if run_artifacts.config.label_column != "is_attack":
        parser.error(
            f"run {args.run_id!r} was trained on label_column="
            f"{run_artifacts.config.label_column!r}; this evaluator currently supports "
            "is_attack (binary) runs only -- see nids/evaluation/attack.py's module docstring."
        )

    train_df = load_train(full=run_artifacts.config.train_full)
    test_df = load_test(exclude_difficulty_21=(args.test_file == "difficulty-21"))
    bounds = FeatureBounds.from_train_df(train_df)
    budgets = _parse_budgets(args.budgets)

    attack_run = run_attack(
        model=run_artifacts.model,
        feature_engineer=run_artifacts.feature_engineer,
        test_df=test_df,
        bounds=bounds,
        budgets=budgets,
        n_trials=args.n_trials,
        random_state=args.seed,
        max_rows=args.max_rows,
    )

    report = {
        "run_id": args.run_id,
        "model_name": run_artifacts.config.model_name,
        "test_file": "KDDTest-21.txt" if args.test_file == "difficulty-21" else "KDDTest+.txt",
        "budgets": budgets,
        "n_trials": args.n_trials,
        "seed": args.seed,
        "evasion_summary": evasion_summary(
            attack_run.results, attack_run.n_true_positives, attack_run.n_baseline_negatives
        ),
        "category_breakdown": category_breakdown(attack_run.results, test_df),
        "feature_association": feature_association(attack_run.results),
        "shap_overlap": shap_overlap(
            run_artifacts.model,
            run_artifacts.feature_engineer,
            test_df,
            attack_run.results,
            top_n=args.top_n_shap,
        ),
    }

    print(json.dumps(report["evasion_summary"], indent=2))

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2))
        print(f"full report written to {args.output}")

    return 0
