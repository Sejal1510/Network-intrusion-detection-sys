from pathlib import Path

import pytest
from mlflow.tracking import MlflowClient

from nids.data import loader
from nids.training import run as run_module
from nids.training.config import TrainingConfig
from nids.training.run import run_training

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd.txt"


@pytest.fixture
def fixture_df():
    return loader._read_nsl_kdd_file(FIXTURE)


def test_run_training_end_to_end_with_injected_data(fixture_df, tmp_path):
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        artifact_root=tmp_path / "runs",
    )

    run_artifacts = run_training(
        config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False
    )

    assert run_artifacts.run_dir.exists()
    assert (run_artifacts.run_dir / "model.joblib").exists()
    assert (run_artifacts.run_dir / "feature_pipeline.joblib").exists()
    assert "accuracy" in run_artifacts.metrics
    assert run_artifacts.metadata["run_id"] == run_artifacts.run_dir.name
    assert run_artifacts.metadata["model_name"] == "random_forest"


def test_run_training_respects_explicit_run_name(fixture_df, tmp_path):
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        artifact_root=tmp_path / "runs",
        run_name="my-fixed-run",
    )

    run_artifacts = run_training(
        config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False
    )

    assert run_artifacts.run_dir.name == "my-fixed-run"
    assert run_artifacts.run_dir == tmp_path / "runs" / "my-fixed-run"


def test_run_training_supports_multiclass_label_column(fixture_df, tmp_path):
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        artifact_root=tmp_path / "runs",
        label_column="attack_category",
    )

    run_artifacts = run_training(
        config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False
    )

    assert "precision_macro" in run_artifacts.metrics
    assert "precision_binary" not in run_artifacts.metrics


def test_run_training_two_models_share_identical_feature_pipeline_shape(fixture_df, tmp_path):
    """Benchmarking a second model is purely a config change -- both runs
    must consume the same feature contract."""
    base_kwargs = {"train_df": fixture_df, "test_df": fixture_df, "log_to_mlflow": False}

    rf_artifacts = run_training(
        TrainingConfig(
            model_name="random_forest",
            model_params={"n_estimators": 5},
            artifact_root=tmp_path / "runs",
            run_name="rf-run",
        ),
        **base_kwargs,
    )
    cb_artifacts = run_training(
        TrainingConfig(
            model_name="catboost",
            model_params={"iterations": 10, "depth": 2},
            artifact_root=tmp_path / "runs",
            run_name="cb-run",
        ),
        **base_kwargs,
    )

    assert rf_artifacts.feature_engineer.feature_names_out == cb_artifacts.feature_engineer.feature_names_out


def test_run_training_logs_to_mlflow_when_enabled(fixture_df, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tracking_uri = f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}"

    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        artifact_root=tmp_path / "runs",
        experiment_name="nids-run-test",
        tracking_uri=tracking_uri,
    )

    run_artifacts = run_training(config, train_df=fixture_df, test_df=fixture_df)

    client = MlflowClient(tracking_uri=tracking_uri)
    experiment = client.get_experiment_by_name("nids-run-test")
    assert experiment is not None
    runs = client.search_runs([experiment.experiment_id])
    assert len(runs) == 1
    assert runs[0].data.params["model_name"] == "random_forest"
    assert runs[0].data.metrics["accuracy"] == pytest.approx(run_artifacts.metrics["accuracy"])


def test_cli_main_runs_end_to_end_with_monkeypatched_data(fixture_df, tmp_path, monkeypatch):
    from nids.training import cli as cli_module

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run_module, "load_train", lambda full: fixture_df)
    monkeypatch.setattr(run_module, "load_test", lambda exclude_difficulty_21: fixture_df)
    monkeypatch.setattr(
        "sys.argv", ["nids-train", "--model", "random_forest", "--quick", "--no-mlflow"]
    )

    exit_code = cli_module.main()
    assert exit_code == 0
