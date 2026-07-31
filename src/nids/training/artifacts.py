"""Persist and reload everything needed to reproduce a training run.

A run directory is self-contained. For a single train/test split
(`save_run`/`load_run`): the trained model, the exact fitted
FeatureEngineer it was trained against, the config that produced it, the
metrics it scored, and metadata (versions, timestamps, git commit). For
cross-validation (`save_cv_run`/`load_cv_run`): the same config/metadata
shape, but metrics are per-fold + aggregated rather than a single model's
score -- there is no single fold-independent model or feature pipeline to
save, since each fold fits its own from scratch (see
nids.training.validation). For hyperparameter search
(`save_tuning_run`/`load_tuning_run`): the base config, the search space,
and a lightweight index of every trial (params/run_id/score) -- each
trial is itself a full CV run, saved separately via `save_cv_run` and
reachable in full via its `run_id`, so per-fold detail is never duplicated
between a trial and the study that ran it.

All three run types share the same directory conventions (config.json,
metrics.json or trials.json, metadata.json) and the same core metadata
fields wherever they apply, so comparing runs of different types is a
matter of reading the same files, not learning three formats.
"""

from __future__ import annotations

import json
import platform
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import joblib
import sklearn

from nids.features import FeatureEngineer
from nids.models.registry import Classifier
from nids.training.config import TrainingConfig

if TYPE_CHECKING:
    from nids.training.tuning import TuningResult
    from nids.training.validation import CVResult

MODEL_FILENAME = "model.joblib"
FEATURE_PIPELINE_FILENAME = "feature_pipeline.joblib"
CONFIG_FILENAME = "config.json"
METRICS_FILENAME = "metrics.json"
METADATA_FILENAME = "metadata.json"
SEARCH_SPACE_FILENAME = "search_space.json"
TRIALS_FILENAME = "trials.json"


@dataclass(frozen=True)
class RunArtifacts:
    run_dir: Path
    model: Classifier
    feature_engineer: FeatureEngineer
    config: TrainingConfig
    metrics: dict[str, Any]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class CVRunArtifacts:
    run_dir: Path
    config: TrainingConfig
    n_folds: int
    fold_metrics: list[dict[str, Any]]
    aggregated_metrics: dict[str, dict[str, float]]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class TuningRunArtifacts:
    run_dir: Path
    base_config: TrainingConfig
    search_space: dict[str, list[Any]]
    trials: list[dict[str, Any]]
    metadata: dict[str, Any]


def default_run_id(model_name: str, suffix: str | None = None) -> str:
    """A timestamped default run id, shared by single-split and
    cross-validation orchestration so the two naming schemes never drift
    apart. `suffix` (e.g. "cv") distinguishes run types at a glance in a
    run-directory listing or the MLflow UI."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    parts = [model_name, *([suffix] if suffix else []), timestamp]
    return "_".join(parts)


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


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2))


def _base_metadata(config: TrainingConfig, run_id: str) -> dict[str, Any]:
    """Metadata fields common to every run type."""
    return {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_name": config.model_name,
        "random_seed": config.random_seed,
        "label_column": config.label_column,
        "python_version": platform.python_version(),
        "sklearn_version": sklearn.__version__,
        "git_commit": _git_commit(),
    }


def save_run(
    run_dir: str | Path,
    model: Classifier,
    feature_engineer: FeatureEngineer,
    config: TrainingConfig,
    metrics: dict[str, Any],
) -> RunArtifacts:
    """Write a complete, self-contained single train/test split run
    directory. `feature_engineer` must already be fitted (it is the exact
    pipeline `model` was trained against)."""
    if not feature_engineer.is_fitted:
        raise RuntimeError("Cannot save a run with an unfitted FeatureEngineer.")

    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(model, run_dir / MODEL_FILENAME)
    feature_engineer.save(run_dir / FEATURE_PIPELINE_FILENAME)
    _write_json(run_dir / CONFIG_FILENAME, config.to_dict())
    _write_json(run_dir / METRICS_FILENAME, metrics)

    metadata = {
        **_base_metadata(config, run_dir.name),
        "run_type": "single_split",
        "feature_schema_version": feature_engineer.fit_metadata.get("schema_version"),
        "n_features": len(feature_engineer.feature_names_out),
    }
    _write_json(run_dir / METADATA_FILENAME, metadata)

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


def save_cv_run(run_dir: str | Path, cv_result: CVResult) -> CVRunArtifacts:
    """Write a complete, self-contained cross-validation run directory.

    No model or feature pipeline is saved: cross-validation fits a fresh
    one per fold specifically to measure how well the config generalizes,
    not to produce a single deployable model (see
    nids.training.validation.run_cross_validation). To get a deployable
    model out of the same config, run `nids.training.run.run_training`.
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    config = cv_result.config

    _write_json(run_dir / CONFIG_FILENAME, config.to_dict())
    _write_json(
        run_dir / METRICS_FILENAME,
        {
            "fold_metrics": cv_result.fold_metrics,
            "aggregated_metrics": cv_result.aggregated_metrics,
        },
    )

    metadata = {
        **_base_metadata(config, run_dir.name),
        "run_type": "cross_validation",
        "n_folds": cv_result.n_folds,
    }
    _write_json(run_dir / METADATA_FILENAME, metadata)

    return CVRunArtifacts(
        run_dir=run_dir,
        config=config,
        n_folds=cv_result.n_folds,
        fold_metrics=cv_result.fold_metrics,
        aggregated_metrics=cv_result.aggregated_metrics,
        metadata=metadata,
    )


def load_cv_run(run_dir: str | Path) -> CVRunArtifacts:
    """Reload a run directory written by `save_cv_run` in full."""
    run_dir = Path(run_dir)

    config_data = json.loads((run_dir / CONFIG_FILENAME).read_text())
    config_data["artifact_root"] = Path(config_data["artifact_root"])
    config = TrainingConfig(**config_data)

    metrics_data = json.loads((run_dir / METRICS_FILENAME).read_text())
    metadata = json.loads((run_dir / METADATA_FILENAME).read_text())

    return CVRunArtifacts(
        run_dir=run_dir,
        config=config,
        n_folds=metadata["n_folds"],
        fold_metrics=metrics_data["fold_metrics"],
        aggregated_metrics=metrics_data["aggregated_metrics"],
        metadata=metadata,
    )


def save_tuning_run(run_dir: str | Path, tuning_result: TuningResult) -> TuningRunArtifacts:
    """Write a complete, self-contained hyperparameter-search run
    directory: the base config, the search space, a lightweight per-trial
    summary (params/run_id/score), and metadata identifying the winner.

    Each trial is *also* saved individually as its own full CV run (see
    `save_cv_run`, called once per trial by
    `nids.training.tuning.run_hyperparameter_search`) -- this function
    does not duplicate that per-trial fold-level detail, it only indexes
    it by `run_id` so the full detail is one `load_cv_run` away.
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    config = tuning_result.base_config

    _write_json(run_dir / CONFIG_FILENAME, config.to_dict())
    _write_json(run_dir / SEARCH_SPACE_FILENAME, tuning_result.search_space)

    trial_summaries = [
        {
            "trial_index": trial.trial_index,
            "params": trial.params,
            "run_id": trial.config.run_name,
            "score": trial.score,
        }
        for trial in tuning_result.trials
    ]
    _write_json(run_dir / TRIALS_FILENAME, trial_summaries)

    metadata = {
        **_base_metadata(config, run_dir.name),
        "run_type": "hyperparameter_search",
        "strategy_name": tuning_result.strategy_name,
        "metric": tuning_result.metric,
        "maximize": tuning_result.maximize,
        "n_trials": len(tuning_result.trials),
        "best_trial_run_id": tuning_result.best_trial.config.run_name,
        "best_params": tuning_result.best_trial.params,
        "best_score": tuning_result.best_trial.score,
    }
    _write_json(run_dir / METADATA_FILENAME, metadata)

    return TuningRunArtifacts(
        run_dir=run_dir,
        base_config=config,
        search_space=tuning_result.search_space,
        trials=trial_summaries,
        metadata=metadata,
    )


def load_tuning_run(run_dir: str | Path) -> TuningRunArtifacts:
    """Reload a run directory written by `save_tuning_run` in full. Use
    `load_cv_run(run_dir.parent / trial["run_id"])` to get a given trial's
    full per-fold detail."""
    run_dir = Path(run_dir)

    config_data = json.loads((run_dir / CONFIG_FILENAME).read_text())
    config_data["artifact_root"] = Path(config_data["artifact_root"])
    base_config = TrainingConfig(**config_data)

    search_space = json.loads((run_dir / SEARCH_SPACE_FILENAME).read_text())
    trials = json.loads((run_dir / TRIALS_FILENAME).read_text())
    metadata = json.loads((run_dir / METADATA_FILENAME).read_text())

    return TuningRunArtifacts(
        run_dir=run_dir,
        base_config=base_config,
        search_space=search_space,
        trials=trials,
        metadata=metadata,
    )
