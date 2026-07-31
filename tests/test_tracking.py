from pathlib import Path

import mlflow
import pytest
from mlflow.tracking import MlflowClient

from nids.data import loader
from nids.features import FeatureEngineer
from nids.models.registry import build_model
from nids.training.artifacts import save_cv_run, save_run, save_tuning_run
from nids.training.config import TrainingConfig
from nids.training.evaluate import evaluate_classifier
from nids.training.search import GridSearch
from nids.training.tracking import log_cv_run, log_run, log_tuning_run
from nids.training.tuning import search_hyperparameters
from nids.training.validation import run_cross_validation

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd.txt"
CV_FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd_cv.txt"


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
    assert run.data.tags["run_type"] == "single_split"
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


@pytest.fixture
def cv_run_artifacts(tmp_path):
    df = loader._read_nsl_kdd_file(CV_FIXTURE)
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        cv_folds=3,
        experiment_name="nids-test-experiment",
        tracking_uri=_sqlite_uri(tmp_path),
    )
    cv_result = run_cross_validation(config, df=df)
    return save_cv_run(tmp_path / "cv-run-tracking", cv_result)


def test_log_cv_run_records_aggregated_metrics_tags_and_artifacts(cv_run_artifacts):
    run_id = log_cv_run(cv_run_artifacts)

    client = MlflowClient(tracking_uri=cv_run_artifacts.config.tracking_uri)
    run = client.get_run(run_id)

    accuracy_stats = cv_run_artifacts.aggregated_metrics["accuracy"]
    assert run.data.metrics["accuracy"] == pytest.approx(accuracy_stats["mean"])
    assert run.data.metrics["accuracy_std"] == pytest.approx(accuracy_stats["std"])
    assert run.data.metrics["accuracy_min"] == pytest.approx(accuracy_stats["min"])
    assert run.data.metrics["accuracy_max"] == pytest.approx(accuracy_stats["max"])

    assert run.data.tags["model_name"] == "random_forest"
    assert run.data.tags["run_type"] == "cross_validation"
    assert run.data.tags["cv_folds"] == "3"

    artifact_paths = {f.path for f in client.list_artifacts(run_id)}
    assert "config.json" in artifact_paths
    assert "metrics.json" in artifact_paths
    assert "metadata.json" in artifact_paths
    assert "model.joblib" not in artifact_paths  # no single model for a CV run


def test_log_cv_run_metric_names_match_log_run_for_comparability(cv_run_artifacts, run_artifacts):
    """A CV run's 'accuracy' and a single-split run's 'accuracy' must be the
    same metric name, so the two show up comparably in the same MLflow
    table column -- that's the whole point of sharing this metric shape."""
    cv_run_id = log_cv_run(cv_run_artifacts)
    single_run_id = log_run(run_artifacts, tracking_uri=cv_run_artifacts.config.tracking_uri)

    client = MlflowClient(tracking_uri=cv_run_artifacts.config.tracking_uri)
    cv_run = client.get_run(cv_run_id)
    single_run = client.get_run(single_run_id)

    assert "accuracy" in cv_run.data.metrics
    assert "accuracy" in single_run.data.metrics


@pytest.fixture
def tuning_artifacts(tmp_path):
    df = loader._read_nsl_kdd_file(CV_FIXTURE)
    config = TrainingConfig(
        model_name="random_forest",
        cv_folds=3,
        experiment_name="nids-test-experiment",
        tracking_uri=_sqlite_uri(tmp_path),
    )
    tuning_result = search_hyperparameters(config, {"n_estimators": [5, 10]}, GridSearch(), df=df)

    trial_cv_artifacts = [
        save_cv_run(tmp_path / "runs" / trial.config.run_name, trial.cv_result)
        for trial in tuning_result.trials
    ]
    tuning_run_artifacts = save_tuning_run(tmp_path / "runs" / tuning_result.study_run_id, tuning_result)
    return tuning_run_artifacts, trial_cv_artifacts


def test_log_tuning_run_creates_parent_and_nested_child_runs(tuning_artifacts):
    tuning_run_artifacts, trial_cv_artifacts = tuning_artifacts

    parent_run_id = log_tuning_run(tuning_run_artifacts, trial_cv_artifacts)

    client = MlflowClient(tracking_uri=tuning_run_artifacts.base_config.tracking_uri)
    parent_run = client.get_run(parent_run_id)

    assert parent_run.data.tags["run_type"] == "hyperparameter_search"
    assert parent_run.data.params["strategy_name"] == "GridSearch"
    assert parent_run.data.metrics["best_score"] == pytest.approx(
        tuning_run_artifacts.metadata["best_score"]
    )

    experiment_id = parent_run.info.experiment_id
    all_runs = client.search_runs([experiment_id])
    child_runs = [r for r in all_runs if r.data.tags.get("mlflow.parentRunId") == parent_run_id]
    assert len(child_runs) == len(trial_cv_artifacts)
    for child in child_runs:
        assert child.data.tags["run_type"] == "cross_validation"


def test_log_tuning_run_logs_study_level_artifacts(tuning_artifacts):
    tuning_run_artifacts, trial_cv_artifacts = tuning_artifacts

    parent_run_id = log_tuning_run(tuning_run_artifacts, trial_cv_artifacts)

    client = MlflowClient(tracking_uri=tuning_run_artifacts.base_config.tracking_uri)
    artifact_paths = {f.path for f in client.list_artifacts(parent_run_id)}

    assert "config.json" in artifact_paths
    assert "search_space.json" in artifact_paths
    assert "trials.json" in artifact_paths
    assert "metadata.json" in artifact_paths
