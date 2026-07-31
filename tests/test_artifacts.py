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
    load_run,
    save_run,
)
from nids.training.config import TrainingConfig
from nids.training.evaluate import evaluate_classifier

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd.txt"


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
    assert metadata["model_name"] == "random_forest"
    assert metadata["feature_schema_version"] == fe.fit_metadata["schema_version"]
    assert metadata["n_features"] == len(fe.feature_names_out)
    assert "python_version" in metadata
    assert "sklearn_version" in metadata
    assert "git_commit" in metadata  # value may be None outside a git repo
