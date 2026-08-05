from pathlib import Path

import pytest
from fastapi import FastAPI

from nids.api import cli as cli_module
from nids.data import loader
from nids.training.config import TrainingConfig
from nids.training.run import run_training

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd.txt"

_NIDS_ENV_VARS = (
    "NIDS_RUN_ID",
    "NIDS_ANOMALY_RUN_ID",
    "NIDS_ARTIFACT_ROOT",
    "NIDS_HOST",
    "NIDS_PORT",
    "NIDS_DATABASE_URL",
    "NIDS_ALERT_THRESHOLD",
    "NIDS_CORS_ORIGINS",
    "NIDS_SECRET_KEY",
    "NIDS_LOG_LEVEL",
    "NIDS_LOG_FORMAT",
    "NIDS_PAIRING_RATE_LIMIT_PER_MINUTE",
    "NIDS_INFERENCE_RATE_LIMIT_PER_MINUTE",
    "NIDS_MAX_UPLOAD_SIZE_BYTES",
)


@pytest.fixture(autouse=True)
def _clean_nids_env(monkeypatch):
    """Every test gets a blank slate regardless of the host shell's own
    environment -- CLI env-var fallbacks are exercised explicitly per test."""
    for name in _NIDS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


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


def test_cli_main_wires_secret_key(trained_run_dir, monkeypatch):
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
            "--secret-key",
            "a-stable-secret",
        ],
    )

    cli_module.main()

    assert calls["app"].state.secret_key == "a-stable-secret"


def test_cli_main_reads_run_id_from_env(trained_run_dir, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli_module.uvicorn, "run", lambda app, host, port: calls.update(app=app))
    monkeypatch.setenv("NIDS_RUN_ID", "cli-fixture-run")
    monkeypatch.setenv("NIDS_ARTIFACT_ROOT", str(trained_run_dir))
    monkeypatch.setattr("sys.argv", ["nids-api"])

    exit_code = cli_module.main()

    assert exit_code == 0
    assert calls["app"].state.served_ensemble.classifier.run_id == "cli-fixture-run"


def test_cli_main_flag_overrides_env_var(trained_run_dir, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli_module.uvicorn, "run", lambda app, host, port: calls.update(app=app))
    monkeypatch.setenv("NIDS_PORT", "9999")
    monkeypatch.setattr(
        "sys.argv",
        [
            "nids-api",
            "--run-id",
            "cli-fixture-run",
            "--artifact-root",
            str(trained_run_dir),
            "--port",
            "8500",
        ],
    )

    cli_module.main()

    assert calls["app"].state.serving_config.port == 8500


def test_cli_main_wires_env_var_database_and_cors_and_threshold(trained_run_dir, tmp_path, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli_module.uvicorn, "run", lambda app, host, port: calls.update(app=app))
    monkeypatch.setenv("NIDS_RUN_ID", "cli-fixture-run")
    monkeypatch.setenv("NIDS_ARTIFACT_ROOT", str(trained_run_dir))
    monkeypatch.setenv("NIDS_DATABASE_URL", f"sqlite:///{tmp_path / 'history.db'}")
    monkeypatch.setenv("NIDS_CORS_ORIGINS", "http://localhost:5173, http://localhost:4173")
    monkeypatch.setenv("NIDS_ALERT_THRESHOLD", "42")
    monkeypatch.setattr("sys.argv", ["nids-api"])

    cli_module.main()

    config = calls["app"].state.serving_config
    assert calls["app"].state.db_engine is not None
    assert config.cors_origins == ("http://localhost:5173", "http://localhost:4173")
    assert config.alert_threshold == 42.0


def test_cli_main_wires_rate_limit_and_upload_size_flags(trained_run_dir, monkeypatch):
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
            "--pairing-rate-limit",
            "5",
            "--inference-rate-limit",
            "50",
            "--max-upload-size",
            "1000",
        ],
    )

    cli_module.main()

    config = calls["app"].state.serving_config
    assert config.pairing_rate_limit_per_minute == 5
    assert config.inference_rate_limit_per_minute == 50
    assert config.max_upload_size_bytes == 1000


def test_cli_main_defaults_rate_limits_and_upload_size(trained_run_dir, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli_module.uvicorn, "run", lambda app, host, port: calls.update(app=app))
    monkeypatch.setattr(
        "sys.argv",
        ["nids-api", "--run-id", "cli-fixture-run", "--artifact-root", str(trained_run_dir)],
    )

    cli_module.main()

    config = calls["app"].state.serving_config
    assert config.pairing_rate_limit_per_minute == 20
    assert config.inference_rate_limit_per_minute == 120
    assert config.max_upload_size_bytes == 10_000_000


def test_cli_main_reads_rate_limits_and_upload_size_from_env(trained_run_dir, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli_module.uvicorn, "run", lambda app, host, port: calls.update(app=app))
    monkeypatch.setenv("NIDS_RUN_ID", "cli-fixture-run")
    monkeypatch.setenv("NIDS_ARTIFACT_ROOT", str(trained_run_dir))
    monkeypatch.setenv("NIDS_PAIRING_RATE_LIMIT_PER_MINUTE", "5")
    monkeypatch.setenv("NIDS_INFERENCE_RATE_LIMIT_PER_MINUTE", "50")
    monkeypatch.setenv("NIDS_MAX_UPLOAD_SIZE_BYTES", "1000")
    monkeypatch.setattr("sys.argv", ["nids-api"])

    cli_module.main()

    config = calls["app"].state.serving_config
    assert config.pairing_rate_limit_per_minute == 5
    assert config.inference_rate_limit_per_minute == 50
    assert config.max_upload_size_bytes == 1000


def test_cli_main_flag_overrides_env_for_rate_limits(trained_run_dir, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli_module.uvicorn, "run", lambda app, host, port: calls.update(app=app))
    monkeypatch.setenv("NIDS_PAIRING_RATE_LIMIT_PER_MINUTE", "5")
    monkeypatch.setattr(
        "sys.argv",
        [
            "nids-api",
            "--run-id",
            "cli-fixture-run",
            "--artifact-root",
            str(trained_run_dir),
            "--pairing-rate-limit",
            "7",
        ],
    )

    cli_module.main()

    assert calls["app"].state.serving_config.pairing_rate_limit_per_minute == 7


def test_cli_main_wires_log_level_and_format(trained_run_dir, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli_module.uvicorn, "run", lambda app, host, port: None)
    monkeypatch.setattr(
        cli_module, "setup_logging", lambda level, json_format: calls.update(level=level, json_format=json_format)
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "nids-api",
            "--run-id",
            "cli-fixture-run",
            "--artifact-root",
            str(trained_run_dir),
            "--log-level",
            "DEBUG",
            "--log-format",
            "json",
        ],
    )

    cli_module.main()

    assert calls == {"level": "DEBUG", "json_format": True}


def test_cli_main_defaults_to_info_and_text_log_format(trained_run_dir, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli_module.uvicorn, "run", lambda app, host, port: None)
    monkeypatch.setattr(
        cli_module, "setup_logging", lambda level, json_format: calls.update(level=level, json_format=json_format)
    )
    monkeypatch.setattr(
        "sys.argv",
        ["nids-api", "--run-id", "cli-fixture-run", "--artifact-root", str(trained_run_dir)],
    )

    cli_module.main()

    assert calls == {"level": "INFO", "json_format": False}


def test_cli_main_reads_log_level_and_format_from_env(trained_run_dir, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli_module.uvicorn, "run", lambda app, host, port: None)
    monkeypatch.setattr(
        cli_module, "setup_logging", lambda level, json_format: calls.update(level=level, json_format=json_format)
    )
    monkeypatch.setenv("NIDS_RUN_ID", "cli-fixture-run")
    monkeypatch.setenv("NIDS_ARTIFACT_ROOT", str(trained_run_dir))
    monkeypatch.setenv("NIDS_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("NIDS_LOG_FORMAT", "json")
    monkeypatch.setattr("sys.argv", ["nids-api"])

    cli_module.main()

    assert calls == {"level": "WARNING", "json_format": True}


def test_cli_main_flag_overrides_env_for_log_level(trained_run_dir, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli_module.uvicorn, "run", lambda app, host, port: None)
    monkeypatch.setattr(
        cli_module, "setup_logging", lambda level, json_format: calls.update(level=level, json_format=json_format)
    )
    monkeypatch.setenv("NIDS_LOG_LEVEL", "WARNING")
    monkeypatch.setattr(
        "sys.argv",
        [
            "nids-api",
            "--run-id",
            "cli-fixture-run",
            "--artifact-root",
            str(trained_run_dir),
            "--log-level",
            "ERROR",
        ],
    )

    cli_module.main()

    assert calls["level"] == "ERROR"


def test_cli_main_requires_run_id_from_flag_or_env(trained_run_dir, monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.argv", ["nids-api", "--artifact-root", str(trained_run_dir)]
    )

    with pytest.raises(SystemExit) as exc_info:
        cli_module.main()

    assert exc_info.value.code == 2
    assert "--run-id is required" in capsys.readouterr().err
