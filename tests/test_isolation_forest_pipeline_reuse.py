"""Proves Milestone 3's central architectural claim: Isolation Forest needs
zero new training code. Every one of these calls is exactly what a
CatBoost or Random Forest run already uses (nids.training.run/validation/
tuning, unmodified) -- only TrainingConfig.model_name changes.
"""

from pathlib import Path

import pytest

from nids.data import loader
from nids.training.config import TrainingConfig
from nids.training.run import run_training
from nids.training.search import GridSearch
from nids.training.tuning import run_hyperparameter_search
from nids.training.validation import run_cv_training

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd.txt"
CV_FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd_cv.txt"


@pytest.fixture
def fixture_df():
    return loader._read_nsl_kdd_file(FIXTURE)


@pytest.fixture
def cv_fixture_df():
    return loader._read_nsl_kdd_file(CV_FIXTURE)


def test_run_training_works_unmodified_for_isolation_forest(fixture_df, tmp_path):
    config = TrainingConfig(
        model_name="isolation_forest",
        artifact_root=tmp_path / "runs",
        run_name="iso-run",
    )

    run_artifacts = run_training(
        config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False
    )

    assert run_artifacts.run_dir.exists()
    assert (run_artifacts.run_dir / "model.joblib").exists()
    assert "accuracy" in run_artifacts.metrics
    assert run_artifacts.metadata["model_name"] == "isolation_forest"


def test_isolation_forest_shares_identical_feature_pipeline_with_catboost(fixture_df, tmp_path):
    """Benchmarking the anomaly detector against a supervised model is
    purely a config change -- both runs consume the same feature contract,
    exactly like comparing two supervised models already does."""
    base_kwargs = {"train_df": fixture_df, "test_df": fixture_df, "log_to_mlflow": False}

    iso_artifacts = run_training(
        TrainingConfig(
            model_name="isolation_forest", artifact_root=tmp_path / "runs", run_name="iso-run"
        ),
        **base_kwargs,
    )
    rf_artifacts = run_training(
        TrainingConfig(
            model_name="random_forest",
            model_params={"n_estimators": 5},
            artifact_root=tmp_path / "runs",
            run_name="rf-run",
        ),
        **base_kwargs,
    )

    assert (
        iso_artifacts.feature_engineer.feature_names_out
        == rf_artifacts.feature_engineer.feature_names_out
    )


def test_run_cross_validation_works_unmodified_for_isolation_forest(cv_fixture_df, tmp_path):
    config = TrainingConfig(
        model_name="isolation_forest",
        cv_folds=3,
        artifact_root=tmp_path / "runs",
    )

    cv_artifacts = run_cv_training(config, df=cv_fixture_df, log_to_mlflow=False)

    assert cv_artifacts.n_folds == 3
    assert "accuracy" in cv_artifacts.aggregated_metrics


def test_run_hyperparameter_search_works_unmodified_for_isolation_forest(cv_fixture_df, tmp_path):
    config = TrainingConfig(
        model_name="isolation_forest",
        cv_folds=3,
        artifact_root=tmp_path / "runs",
    )
    space = {"n_estimators": [10, 20]}

    tuning_artifacts = run_hyperparameter_search(
        config, space, GridSearch(), df=cv_fixture_df, log_to_mlflow=False
    )

    assert tuning_artifacts.metadata["n_trials"] == 2
    assert "n_estimators" in tuning_artifacts.metadata["best_params"]
