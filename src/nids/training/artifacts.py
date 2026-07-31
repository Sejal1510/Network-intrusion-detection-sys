"""Persist and reload everything needed to reproduce a training run.

A run directory is self-contained: the trained model, the exact fitted
FeatureEngineer it was trained against, the config that produced it, the
metrics it scored, and enough metadata (versions, timestamps, git commit) to
tell two runs apart later. `load_run` is the single entry point anything
(a benchmark script, a future inference service) needs to get a working
model + feature pipeline pair back.
"""

from __future__ import annotations

import json
import platform
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import sklearn

from nids.features import FeatureEngineer
from nids.models.registry import Classifier
from nids.training.config import TrainingConfig

MODEL_FILENAME = "model.joblib"
FEATURE_PIPELINE_FILENAME = "feature_pipeline.joblib"
CONFIG_FILENAME = "config.json"
METRICS_FILENAME = "metrics.json"
METADATA_FILENAME = "metadata.json"


@dataclass(frozen=True)
class RunArtifacts:
    run_dir: Path
    model: Classifier
    feature_engineer: FeatureEngineer
    config: TrainingConfig
    metrics: dict[str, Any]
    metadata: dict[str, Any]


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def save_run(
    run_dir: str | Path,
    model: Classifier,
    feature_engineer: FeatureEngineer,
    config: TrainingConfig,
    metrics: dict[str, Any],
) -> RunArtifacts:
    """Write a complete, self-contained run directory. `feature_engineer`
    must already be fitted (it is the exact pipeline `model` was trained
    against)."""
    if not feature_engineer.is_fitted:
        raise RuntimeError("Cannot save a run with an unfitted FeatureEngineer.")

    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, run_dir / MODEL_FILENAME)
    feature_engineer.save(run_dir / FEATURE_PIPELINE_FILENAME)
    (run_dir / CONFIG_FILENAME).write_text(json.dumps(config.to_dict(), indent=2))
    (run_dir / METRICS_FILENAME).write_text(json.dumps(metrics, indent=2))

    metadata = {
        "run_id": run_dir.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_name": config.model_name,
        "random_seed": config.random_seed,
        "label_column": config.label_column,
        "feature_schema_version": feature_engineer.fit_metadata.get("schema_version"),
        "n_features": len(feature_engineer.feature_names_out),
        "python_version": platform.python_version(),
        "sklearn_version": sklearn.__version__,
        "git_commit": _git_commit(),
    }
    (run_dir / METADATA_FILENAME).write_text(json.dumps(metadata, indent=2))

    return RunArtifacts(
        run_dir=run_dir,
        model=model,
        feature_engineer=feature_engineer,
        config=config,
        metrics=metrics,
        metadata=metadata,
    )


def load_run(run_dir: str | Path) -> RunArtifacts:
    """Reload a run directory written by `save_run` in full."""
    run_dir = Path(run_dir)

    model = joblib.load(run_dir / MODEL_FILENAME)
    feature_engineer = FeatureEngineer.load(run_dir / FEATURE_PIPELINE_FILENAME)

    config_data = json.loads((run_dir / CONFIG_FILENAME).read_text())
    config_data["artifact_root"] = Path(config_data["artifact_root"])
    config = TrainingConfig(**config_data)

    metrics = json.loads((run_dir / METRICS_FILENAME).read_text())
    metadata = json.loads((run_dir / METADATA_FILENAME).read_text())

    return RunArtifacts(
        run_dir=run_dir,
        model=model,
        feature_engineer=feature_engineer,
        config=config,
        metrics=metrics,
        metadata=metadata,
    )
