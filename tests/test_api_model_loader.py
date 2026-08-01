from pathlib import Path

import pytest

from nids.api.config import ServingConfig
from nids.api.model_loader import (
    ServedEnsemble,
    ServedModel,
    load_served_ensemble,
    load_served_model,
)
from nids.data import loader
from nids.training.config import TrainingConfig
from nids.training.run import run_training

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd.txt"


@pytest.fixture
def fixture_df():
    return loader._read_nsl_kdd_file(FIXTURE)


@pytest.fixture
def trained_run_dir(fixture_df, tmp_path):
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        artifact_root=tmp_path / "runs",
        run_name="serving-fixture-run",
    )
    run_training(config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)
    return tmp_path / "runs"


@pytest.fixture
def trained_run_dir_with_anomaly(fixture_df, trained_run_dir):
    anomaly_config = TrainingConfig(
        model_name="isolation_forest",
        artifact_root=trained_run_dir,
        run_name="anomaly-fixture-run",
    )
    run_training(anomaly_config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)
    return trained_run_dir


def test_load_served_model_loads_pinned_run(trained_run_dir):
    config = ServingConfig(run_id="serving-fixture-run", artifact_root=trained_run_dir)

    served = load_served_model(config)

    assert isinstance(served, ServedModel)
    assert served.run_id == "serving-fixture-run"
    assert served.feature_engineer.is_fitted
    assert served.metadata["model_name"] == "random_forest"
    assert "accuracy" in served.metrics


def test_load_served_model_raises_for_unknown_run_id(trained_run_dir):
    config = ServingConfig(run_id="does-not-exist", artifact_root=trained_run_dir)

    with pytest.raises(FileNotFoundError):
        load_served_model(config)


def test_serving_config_run_dir_joins_artifact_root_and_run_id(tmp_path):
    config = ServingConfig(run_id="my-run", artifact_root=tmp_path / "runs")

    assert config.run_dir == tmp_path / "runs" / "my-run"


def test_load_served_ensemble_is_classifier_only_when_anomaly_run_id_unset(trained_run_dir):
    config = ServingConfig(run_id="serving-fixture-run", artifact_root=trained_run_dir)

    ensemble = load_served_ensemble(config)

    assert isinstance(ensemble, ServedEnsemble)
    assert ensemble.classifier.run_id == "serving-fixture-run"
    assert ensemble.anomaly_detector is None


def test_load_served_ensemble_loads_both_runs_when_anomaly_run_id_set(
    trained_run_dir_with_anomaly,
):
    config = ServingConfig(
        run_id="serving-fixture-run",
        anomaly_run_id="anomaly-fixture-run",
        artifact_root=trained_run_dir_with_anomaly,
    )

    ensemble = load_served_ensemble(config)

    assert ensemble.classifier.run_id == "serving-fixture-run"
    assert ensemble.anomaly_detector is not None
    assert ensemble.anomaly_detector.run_id == "anomaly-fixture-run"
    assert ensemble.anomaly_detector.metadata["model_name"] == "isolation_forest"


def test_load_served_ensemble_raises_for_unknown_anomaly_run_id(trained_run_dir):
    config = ServingConfig(
        run_id="serving-fixture-run",
        anomaly_run_id="does-not-exist",
        artifact_root=trained_run_dir,
    )

    with pytest.raises(FileNotFoundError):
        load_served_ensemble(config)
