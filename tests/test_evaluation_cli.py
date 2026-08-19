import json
from pathlib import Path

import pytest

from nids.data import loader
from nids.evaluation import cli as cli_module
from nids.training.config import TrainingConfig
from nids.training.run import run_training

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd_cv.txt"


@pytest.fixture
def fixture_df():
    return loader._read_nsl_kdd_file(FIXTURE)


@pytest.fixture
def trained_run_dir(fixture_df, tmp_path, monkeypatch):
    """A tiny trained run, plus load_train/load_test monkeypatched to
    return the same fixture -- keeps this test fast and independent of
    the full on-disk NSL-KDD dataset."""
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 20},
        label_column="is_attack",
        artifact_root=tmp_path / "runs",
        run_name="adv-eval-fixture-run",
    )
    run_training(config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)

    monkeypatch.setattr(cli_module, "load_train", lambda full: fixture_df)
    monkeypatch.setattr(cli_module, "load_test", lambda exclude_difficulty_21: fixture_df)

    return tmp_path / "runs"


def test_cli_main_writes_report_with_expected_shape(trained_run_dir, tmp_path, monkeypatch, capsys):
    output_path = tmp_path / "report.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "nids-evaluation",
            "--run-id",
            "adv-eval-fixture-run",
            "--artifact-root",
            str(trained_run_dir),
            "--budgets",
            "0.1,0.3",
            "--n-trials",
            "5",
            "--seed",
            "1",
            "--output",
            str(output_path),
        ],
    )

    exit_code = cli_module.main()

    assert exit_code == 0
    report = json.loads(output_path.read_text())
    assert report["run_id"] == "adv-eval-fixture-run"
    assert report["budgets"] == [0.1, 0.3]
    assert set(report) == {
        "run_id", "model_name", "test_file", "budgets", "n_trials", "seed",
        "evasion_summary", "category_breakdown", "feature_association", "shap_overlap",
    }
    printed = capsys.readouterr().out
    assert "baseline_fn_rate" in printed


def test_cli_main_rejects_multiclass_run(fixture_df, tmp_path, monkeypatch):
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        label_column="attack_category",
        artifact_root=tmp_path / "runs",
        run_name="multiclass-fixture-run",
    )
    run_training(config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)

    monkeypatch.setattr(
        "sys.argv",
        [
            "nids-evaluation",
            "--run-id",
            "multiclass-fixture-run",
            "--artifact-root",
            str(tmp_path / "runs"),
        ],
    )

    with pytest.raises(SystemExit):
        cli_module.main()
