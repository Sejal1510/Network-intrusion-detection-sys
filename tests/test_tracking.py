from pathlib import Path

import mlflow
import pytest
from mlflow.tracking import MlflowClient

from nids.data import loader
from nids.features import FeatureEngineer
from nids.models.registry import build_model
from nids.training.artifacts import save_run
from nids.training.config import TrainingConfig
from nids.training.evaluate import evaluate_classifier
from nids.training.tracking import log_run

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd.txt"


@pytest.fixture(autouse=True)
def _isolate_mlflow_artifact_cwd(tmp_path, monkeypatch):
    """MLflow's sqlite backend still writes artifacts to a directory
    relative to the current working directory unless an experiment-level
    artifact_location is configured. Chdir into tmp_path so tests never
    write into the real project's working directory."""
    monkeypatch.chdir(tmp_path)


def _sqlite_uri(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}"


@pytest.fixture
def run_artifacts(tmp_path):
    df = loader._read_nsl_kdd_file(FIXTURE)
    y = df["is_attack"].to_numpy()

    fe = FeatureEngineer().fit(df)
    matrix = fe.transform(df)

    model = build_model("random_forest", random_state=42, n_estimators=5)
    model.fit(matrix.X, y)

    metrics = evaluate_classifier(y, model.predict(matrix.X))
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        experiment_name="nids-test-experiment",
        tracking_uri=_sqlite_uri(tmp_path),
    )

    return save_run(tmp_path / "run-tracking", model, fe, config, metrics)


def test_log_run_records_params_metrics_tags_and_artifacts(run_artifacts, tmp_path):
    run_id = log_run(run_artifacts)

    client = MlflowClient(tracking_uri=run_artifacts.config.tracking_uri)
    run = client.get_run(run_id)

    assert run.data.params["model_name"] == "random_forest"
    assert run.data.params["model_params.n_estimators"] == "5"
    assert run.data.params["random_seed"] == "42"

    assert run.data.metrics["accuracy"] == pytest.approx(run_artifacts.metrics["accuracy"])
    assert "confusion_matrix" not in run.data.metrics  # nested structures aren't metrics

    assert run.data.tags["model_name"] == "random_forest"
    assert run.data.tags["feature_schema_version"] == str(
        run_artifacts.metadata["feature_schema_version"]
    )

    artifact_paths = {f.path for f in client.list_artifacts(run_id)}
    assert "model.joblib" in artifact_paths
    assert "feature_pipeline.joblib" in artifact_paths
    assert "config.json" in artifact_paths
    assert "metrics.json" in artifact_paths
    assert "metadata.json" in artifact_paths


def test_log_run_uses_experiment_name_from_config(run_artifacts):
    run_id = log_run(run_artifacts)

    mlflow.set_tracking_uri(run_artifacts.config.tracking_uri)
    experiment = mlflow.get_experiment_by_name("nids-test-experiment")
    assert experiment is not None

    client = MlflowClient(tracking_uri=run_artifacts.config.tracking_uri)
    run = client.get_run(run_id)
    assert run.info.experiment_id == experiment.experiment_id


def test_log_run_explicit_tracking_uri_overrides_config(run_artifacts, tmp_path):
    override_uri = _sqlite_uri(tmp_path / "override")
    (tmp_path / "override").mkdir()

    run_id = log_run(run_artifacts, tracking_uri=override_uri)

    client = MlflowClient(tracking_uri=override_uri)
    run = client.get_run(run_id)  # does not raise: run truly lives at override_uri
    assert run.data.params["model_name"] == "random_forest"
