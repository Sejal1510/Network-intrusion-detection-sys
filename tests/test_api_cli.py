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
    assert calls["app"].state.served_ensemble.classifier.run_id == "cli-fixture-run"
    assert calls["app"].state.served_ensemble.anomaly_detector is None
    assert calls["port"] == 9000


def test_cli_main_loads_optional_anomaly_run_id(fixture_df, trained_run_dir, monkeypatch):
    anomaly_config = TrainingConfig(
        model_name="isolation_forest",
        artifact_root=trained_run_dir,
        run_name="cli-anomaly-run",
    )
    run_training(anomaly_config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)

    calls = {}
    monkeypatch.setattr(cli_module.uvicorn, "run", lambda app, host, port: calls.update(app=app))
    monkeypatch.setattr(
        "sys.argv",
        [
            "nids-api",
            "--run-id",
            "cli-fixture-run",
            "--anomaly-run-id",
            "cli-anomaly-run",
            "--artifact-root",
            str(trained_run_dir),
        ],
    )

    exit_code = cli_module.main()

    assert exit_code == 0
    ensemble = calls["app"].state.served_ensemble
    assert ensemble.anomaly_detector is not None
    assert ensemble.anomaly_detector.run_id == "cli-anomaly-run"


def test_cli_main_wires_database_url_and_alert_threshold(trained_run_dir, tmp_path, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli_module.uvicorn, "run", lambda app, host, port: calls.update(app=app))
    monkeypatch.setattr(
        "sys.argv",
        [
            "nids-api",
            "--run-id",
            "cli-fixture-run",
            "--artifact-root",
            str(trained_run_dir),
            "--database-url",
            f"sqlite:///{tmp_path / 'history.db'}",
            "--alert-threshold",
            "50",
        ],
    )

    exit_code = cli_module.main()

    assert exit_code == 0
    assert calls["app"].state.db_engine is not None
    assert calls["app"].state.serving_config.alert_threshold == 50.0


def test_cli_main_defaults_to_no_database(trained_run_dir, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli_module.uvicorn, "run", lambda app, host, port: calls.update(app=app))
    monkeypatch.setattr(
        "sys.argv",
        ["nids-api", "--run-id", "cli-fixture-run", "--artifact-root", str(trained_run_dir)],
    )

    cli_module.main()

    assert calls["app"].state.db_engine is None


def test_cli_main_wires_cors_origins(trained_run_dir, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli_module.uvicorn, "run", lambda app, host, port: calls.update(app=app))
    monkeypatch.setattr(
        "sys.argv",
        [
            "nids-api",
            "--run-id",
            "cli-fixture-run",
            "--artifact-root",
            str(trained_run_dir),
            "--cors-origin",
            "http://localhost:5173",
            "--cors-origin",
            "http://localhost:4173",
        ],
    )

    cli_module.main()

    assert calls["app"].state.serving_config.cors_origins == (
        "http://localhost:5173",
        "http://localhost:4173",
    )


def test_cli_main_defaults_to_no_cors_origins(trained_run_dir, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli_module.uvicorn, "run", lambda app, host, port: calls.update(app=app))
    monkeypatch.setattr(
        "sys.argv",
        ["nids-api", "--run-id", "cli-fixture-run", "--artifact-root", str(trained_run_dir)],
    )

    cli_module.main()

    assert calls["app"].state.serving_config.cors_origins == ()
