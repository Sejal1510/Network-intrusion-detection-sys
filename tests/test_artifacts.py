from pathlib import Path

import numpy as np
import pytest

from nids.data import loader
from nids.features import FeatureEngineer
from nids.models.registry import build_model
from nids.training.artifacts import (
    CONFIG_FILENAME,
    FEATURE_PIPELINE_FILENAME,
    METADATA_FILENAME,
    METRICS_FILENAME,
    MODEL_FILENAME,
    SEARCH_SPACE_FILENAME,
    TRIALS_FILENAME,
    default_run_id,
    load_cv_run,
    load_run,
    load_tuning_run,
    save_cv_run,
    save_run,
    save_tuning_run,
)
from nids.training.config import TrainingConfig
from nids.training.evaluate import evaluate_classifier
from nids.training.search import GridSearch
from nids.training.tuning import search_hyperparameters
from nids.training.validation import run_cross_validation

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd.txt"
CV_FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd_cv.txt"


@pytest.fixture
def trained_run():
    """A minimal, real (not mocked) fitted model + feature engineer, as the
    orchestrator will eventually produce."""
    df = loader._read_nsl_kdd_file(FIXTURE)
    y = df["is_attack"].to_numpy()

    fe = FeatureEngineer().fit(df)
    matrix = fe.transform(df)

    model = build_model("random_forest", random_state=42, n_estimators=5)
    model.fit(matrix.X, y)

    metrics = evaluate_classifier(y, model.predict(matrix.X))
    config = TrainingConfig(model_name="random_forest", model_params={"n_estimators": 5})

    return df, matrix, model, fe, config, metrics


def test_save_run_writes_expected_files(trained_run, tmp_path):
    _, _, model, fe, config, metrics = trained_run
    run_dir = tmp_path / "run-001"

    save_run(run_dir, model, fe, config, metrics)

    assert (run_dir / MODEL_FILENAME).exists()
    assert (run_dir / FEATURE_PIPELINE_FILENAME).exists()
    assert (run_dir / CONFIG_FILENAME).exists()
    assert (run_dir / METRICS_FILENAME).exists()
    assert (run_dir / METADATA_FILENAME).exists()


def test_save_run_rejects_unfitted_feature_engineer(trained_run, tmp_path):
    _, _, model, _, config, metrics = trained_run
    unfitted_fe = FeatureEngineer()

    with pytest.raises(RuntimeError, match="unfitted"):
        save_run(tmp_path / "run-002", model, unfitted_fe, config, metrics)


def test_load_run_reproduces_config_and_predictions(trained_run, tmp_path):
    df, matrix, model, fe, config, metrics = trained_run
    run_dir = tmp_path / "run-003"
    saved = save_run(run_dir, model, fe, config, metrics)

    loaded = load_run(run_dir)

    assert loaded.config == config
    assert loaded.metrics == metrics

    # the reloaded feature engineer + model must reproduce identical predictions
    reloaded_matrix = loaded.feature_engineer.transform(df)
    np.testing.assert_array_equal(loaded.model.predict(reloaded_matrix.X), model.predict(matrix.X))
    assert saved.metadata["run_id"] == "run-003"


def test_metadata_contains_expected_keys(trained_run, tmp_path):
    _, _, model, fe, config, metrics = trained_run
    saved = save_run(tmp_path / "run-004", model, fe, config, metrics)

    metadata = saved.metadata
    assert metadata["run_type"] == "single_split"
    assert metadata["model_name"] == "random_forest"
    assert metadata["feature_schema_version"] == fe.fit_metadata["schema_version"]
    assert metadata["n_features"] == len(fe.feature_names_out)
    assert "python_version" in metadata
    assert "sklearn_version" in metadata
    assert "git_commit" in metadata  # value may be None outside a git repo


def test_default_run_id_distinguishes_run_types():
    single_id = default_run_id("catboost")
    cv_id = default_run_id("catboost", suffix="cv")

    assert single_id.startswith("catboost_")
    assert "cv" not in single_id.split("_")
    assert cv_id.startswith("catboost_cv_")


@pytest.fixture
def cv_result():
    df = loader._read_nsl_kdd_file(CV_FIXTURE)
    config = TrainingConfig(model_name="random_forest", model_params={"n_estimators": 5}, cv_folds=3)
    return run_cross_validation(config, df=df)


def test_save_cv_run_writes_expected_files_and_no_model(cv_result, tmp_path):
    run_dir = tmp_path / "cv-run-001"

    save_cv_run(run_dir, cv_result)

    assert (run_dir / CONFIG_FILENAME).exists()
    assert (run_dir / METRICS_FILENAME).exists()
    assert (run_dir / METADATA_FILENAME).exists()
    # cross-validation fits a fresh model per fold; none of them is "the"
    # deployable model, so neither is persisted at the CV-run level.
    assert not (run_dir / MODEL_FILENAME).exists()
    assert not (run_dir / FEATURE_PIPELINE_FILENAME).exists()


def test_cv_run_metadata_identifies_run_type_and_fold_count(cv_result, tmp_path):
    saved = save_cv_run(tmp_path / "cv-run-002", cv_result)

    assert saved.metadata["run_type"] == "cross_validation"
    assert saved.metadata["n_folds"] == 3
    assert saved.metadata["model_name"] == "random_forest"
    assert "git_commit" in saved.metadata


def test_load_cv_run_reproduces_config_and_metrics(cv_result, tmp_path):
    run_dir = tmp_path / "cv-run-003"
    saved = save_cv_run(run_dir, cv_result)

    loaded = load_cv_run(run_dir)

    assert loaded.config == cv_result.config
    assert loaded.n_folds == cv_result.n_folds
    assert loaded.fold_metrics == cv_result.fold_metrics
    assert loaded.aggregated_metrics == cv_result.aggregated_metrics
    assert loaded.metadata == saved.metadata


@pytest.fixture
def tuning_result():
    df = loader._read_nsl_kdd_file(CV_FIXTURE)
    config = TrainingConfig(model_name="random_forest", cv_folds=3)
    space = {"n_estimators": [5, 10]}
    return search_hyperparameters(config, space, GridSearch(), df=df)


def test_save_tuning_run_writes_expected_files_and_no_model(tuning_result, tmp_path):
    run_dir = tmp_path / "tuning-run-001"

    save_tuning_run(run_dir, tuning_result)

    assert (run_dir / CONFIG_FILENAME).exists()
    assert (run_dir / SEARCH_SPACE_FILENAME).exists()
    assert (run_dir / TRIALS_FILENAME).exists()
    assert (run_dir / METADATA_FILENAME).exists()
    assert not (run_dir / MODEL_FILENAME).exists()
    assert not (run_dir / METRICS_FILENAME).exists()  # tuning uses trials.json, not metrics.json


def test_tuning_run_metadata_identifies_run_type_and_winner(tuning_result, tmp_path):
    saved = save_tuning_run(tmp_path / "tuning-run-002", tuning_result)

    assert saved.metadata["run_type"] == "hyperparameter_search"
    assert saved.metadata["strategy_name"] == "GridSearch"
    assert saved.metadata["n_trials"] == 2
    assert saved.metadata["best_score"] == tuning_result.best_trial.score
    assert saved.metadata["best_params"] == tuning_result.best_trial.params
    assert saved.metadata["best_trial_run_id"] == tuning_result.best_trial.config.run_name


def test_tuning_run_trial_summaries_are_lightweight_and_indexed_by_run_id(tuning_result, tmp_path):
    saved = save_tuning_run(tmp_path / "tuning-run-003", tuning_result)

    assert len(saved.trials) == 2
    for summary, trial in zip(saved.trials, tuning_result.trials, strict=True):
        assert summary["run_id"] == trial.config.run_name
        assert summary["params"] == trial.params
        assert summary["score"] == trial.score
        # lightweight: no fold-level detail duplicated here
        assert "fold_metrics" not in summary
        assert "aggregated_metrics" not in summary


def test_load_tuning_run_reproduces_config_search_space_and_trials(tuning_result, tmp_path):
    run_dir = tmp_path / "tuning-run-004"
    saved = save_tuning_run(run_dir, tuning_result)

    loaded = load_tuning_run(run_dir)

    assert loaded.base_config == tuning_result.base_config
    assert loaded.search_space == tuning_result.search_space
    assert loaded.trials == saved.trials
    assert loaded.metadata == saved.metadata


def test_tuning_trial_run_id_is_reachable_via_load_cv_run(tuning_result, tmp_path):
    """A trial's run_id in trials.json must point at a real, independently
    loadable CV run directory once the orchestrator has saved it."""
    artifact_root = tmp_path / "runs"
    trial = tuning_result.trials[0]
    trial_dir = artifact_root / trial.config.run_name
    save_cv_run(trial_dir, trial.cv_result)

    loaded_trial_cv = load_cv_run(trial_dir)
    assert loaded_trial_cv.aggregated_metrics == trial.cv_result.aggregated_metrics
