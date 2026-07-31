"""MLflow experiment tracking for a completed run.

This is a thin adapter, not a second source of truth: everything logged
here is derived from the same `RunArtifacts` that `nids.training.artifacts`
already wrote to disk. MLflow gets the full picture (params, every scalar
metric, the whole run directory as artifacts, and identifying tags) so runs
are comparable across models/experiments in the MLflow UI, not just a
number or two.
"""

from __future__ import annotations

from numbers import Real
from typing import Any

import mlflow

from nids.training.artifacts import RunArtifacts


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in data.items():
        full_key = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, prefix=f"{full_key}."))
        else:
            flat[full_key] = value
    return flat


def _scalar_metrics(metrics: dict[str, Any]) -> dict[str, float]:
    """MLflow metrics must be plain numbers; metrics.json also holds nested
    structures (confusion_matrix, classification_report, labels) that go to
    MLflow as a logged artifact instead, not as metrics."""
    return {
        key: float(value)
        for key, value in metrics.items()
        if isinstance(value, Real) and not isinstance(value, bool)
    }


def log_run(run_artifacts: RunArtifacts, tracking_uri: str | None = None) -> str:
    """Log a completed run to MLflow. Returns the MLflow run ID.

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
        mlflow.log_metrics(_scalar_metrics(run_artifacts.metrics))
        mlflow.log_artifacts(str(run_artifacts.run_dir))
        mlflow.set_tags(
            {
                "model_name": config.model_name,
                "feature_schema_version": str(run_artifacts.metadata.get("feature_schema_version")),
                "git_commit": run_artifacts.metadata.get("git_commit") or "unknown",
            }
        )
        return run.info.run_id
