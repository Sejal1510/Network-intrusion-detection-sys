"""MLflow experiment tracking for a completed run.

This is a thin adapter, not a second source of truth: everything logged
here is derived from artifacts `nids.training.artifacts` already wrote to
disk -- for a single split (`log_run`/`RunArtifacts`), cross-validation
(`log_cv_run`/`CVRunArtifacts`), or hyperparameter search
(`log_tuning_run`/`TuningRunArtifacts`). All three log the same shape of
thing (flattened config as params, scalar metrics, the whole run directory
as artifacts, identifying tags) so runs of any type are comparable side by
side in the MLflow UI, not just a number or two.

This module is deliberately the only place that imports `mlflow` --
nids.training.run/validation/tuning never touch it directly, so there is
exactly one place tracking behavior can drift.
"""

from __future__ import annotations

from typing import Any

import mlflow

from nids.training.artifacts import CVRunArtifacts, RunArtifacts, TuningRunArtifacts
from nids.training.evaluate import scalar_metrics


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in data.items():
        full_key = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, prefix=f"{full_key}."))
        else:
            flat[full_key] = value
    return flat


def log_run(run_artifacts: RunArtifacts, tracking_uri: str | None = None) -> str:
    """Log a completed single train/test split run to MLflow. Returns the
    MLflow run ID.

    The tracking backend is resolved deterministically from
    `run_artifacts.config.tracking_uri` rather than left to whatever MLflow
    happens to be pointed at by ambient global state -- `tracking_uri`
    overrides that for this call (e.g. tests pointing at a temp directory;
    a deployment pointing at a shared tracking server).
    """
    config = run_artifacts.config
    mlflow.set_tracking_uri(tracking_uri if tracking_uri is not None else config.tracking_uri)
    mlflow.set_experiment(config.experiment_name)

    with mlflow.start_run(run_name=config.run_name or run_artifacts.metadata["run_id"]) as run:
        mlflow.log_params(_flatten(config.to_dict()))
        mlflow.log_metrics(scalar_metrics(run_artifacts.metrics))
        mlflow.log_artifacts(str(run_artifacts.run_dir))
        mlflow.set_tags(
            {
                "model_name": config.model_name,
                "run_type": "single_split",
                "feature_schema_version": str(run_artifacts.metadata.get("feature_schema_version")),
                "git_commit": run_artifacts.metadata.get("git_commit") or "unknown",
            }
        )
        return run.info.run_id


def log_cv_run(
    cv_run_artifacts: CVRunArtifacts,
    tracking_uri: str | None = None,
    nested: bool = False,
) -> str:
    """Log a completed cross-validation run to MLflow. Returns the MLflow
    run ID.

    Each aggregated metric's mean is logged under its own name (e.g.
    `accuracy`) so it lines up in the MLflow UI with the same metric from a
    `log_run` call -- comparing a single split against a CV summary is
    then just comparing two rows of the same table. `_std`/`_min`/`_max`
    are logged alongside for spread; the full per-fold breakdown lives in
    the logged `metrics.json` artifact, not squeezed into MLflow metrics.

    `nested=True` logs this as a child run of whatever MLflow run is
    currently active (used by `log_tuning_run` to group every trial under
    its parent search); the caller is responsible for having an active run
    and a tracking URI already set in that case.
    """
    config = cv_run_artifacts.config
    if not nested:
        mlflow.set_tracking_uri(tracking_uri if tracking_uri is not None else config.tracking_uri)
        mlflow.set_experiment(config.experiment_name)

    with mlflow.start_run(
        run_name=config.run_name or cv_run_artifacts.metadata["run_id"], nested=nested
    ) as run:
        mlflow.log_params(_flatten(config.to_dict()))

        cv_metrics: dict[str, float] = {}
        for key, stats in cv_run_artifacts.aggregated_metrics.items():
            cv_metrics[key] = stats["mean"]
            cv_metrics[f"{key}_std"] = stats["std"]
            cv_metrics[f"{key}_min"] = stats["min"]
            cv_metrics[f"{key}_max"] = stats["max"]
        mlflow.log_metrics(cv_metrics)

        mlflow.log_artifacts(str(cv_run_artifacts.run_dir))
        mlflow.set_tags(
            {
                "model_name": config.model_name,
                "run_type": "cross_validation",
                "cv_folds": str(cv_run_artifacts.n_folds),
                "git_commit": cv_run_artifacts.metadata.get("git_commit") or "unknown",
            }
        )
        return run.info.run_id


def log_tuning_run(
    tuning_run_artifacts: TuningRunArtifacts,
    trial_cv_run_artifacts: list[CVRunArtifacts],
    tracking_uri: str | None = None,
) -> str:
    """Log a completed hyperparameter search to MLflow: one parent run for
    the study (best score/params, the search space, the base config) plus
    one nested child run per trial (via `log_cv_run(..., nested=True)`,
    reusing that function rather than re-implementing per-trial logging).

    Returns the parent run's MLflow run ID.
    """
    config = tuning_run_artifacts.base_config
    mlflow.set_tracking_uri(tracking_uri if tracking_uri is not None else config.tracking_uri)
    mlflow.set_experiment(config.experiment_name)

    metadata = tuning_run_artifacts.metadata
    with mlflow.start_run(run_name=config.run_name or metadata["run_id"]) as run:
        mlflow.log_params(_flatten(config.to_dict()))
        mlflow.log_params(
            {
                "strategy_name": metadata["strategy_name"],
                "metric": metadata["metric"],
                "maximize": metadata["maximize"],
                "n_trials": metadata["n_trials"],
            }
        )
        mlflow.log_metrics({"best_score": metadata["best_score"]})
        mlflow.log_artifacts(str(tuning_run_artifacts.run_dir))
        mlflow.set_tags(
            {
                "model_name": config.model_name,
                "run_type": "hyperparameter_search",
                "best_trial_run_id": metadata["best_trial_run_id"],
                "git_commit": metadata.get("git_commit") or "unknown",
            }
        )

        for trial_cv_artifacts in trial_cv_run_artifacts:
            log_cv_run(trial_cv_artifacts, nested=True)

        return run.info.run_id
