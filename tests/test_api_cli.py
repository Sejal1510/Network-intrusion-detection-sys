from pathlib import Path

import pytest
from fastapi import FastAPI

from nids.api import cli as cli_module
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
        run_name="cli-fixture-run",
    )
    run_training(config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)
    return tmp_path / "runs"


def test_cli_main_loads_pinned_run_and_starts_server(trained_run_dir, monkeypatch):
    calls = {}

    def fake_run(app, host, port):
        calls["app"] = app
        calls["host"] = host
        calls["port"] = port

    monkeypatch.setattr(cli_module.uvicorn, "run", fake_run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "nids-api",
            "--run-id",
            "cli-fixture-run",
            "--artifact-root",
            str(trained_run_dir),
            "--port",
            "9000",
        ],
    )

    exit_code = cli_module.main()

    assert exit_code == 0
    assert isinstance(calls["app"], FastAPI)
    assert calls["app"].state.served_model.run_id == "cli-fixture-run"
    assert calls["port"] == 9000
