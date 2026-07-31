from pathlib import Path

import numpy as np
import pytest

from nids.data import loader
from nids.training import validation as validation_module
from nids.training.config import TrainingConfig
from nids.training.validation import CVResult, _aggregate_fold_metrics, run_cross_validation

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd_cv.txt"


@pytest.fixture
def cv_df():
    return loader._read_nsl_kdd_file(FIXTURE)


def test_run_cross_validation_produces_expected_fold_count(cv_df):
    config = TrainingConfig(model_name="random_forest", model_params={"n_estimators": 5}, cv_folds=3)

    result = run_cross_validation(config, df=cv_df)

    assert isinstance(result, CVResult)
    assert result.n_folds == 3
    assert len(result.fold_metrics) == 3
    assert all("accuracy" in m for m in result.fold_metrics)


def test_run_cross_validation_folds_partition_data_without_overlap(cv_df, monkeypatch):
    """Every row must be used for validation exactly once, and a fold's
    train/validation rows must never overlap each other."""
    seen_val_indices: list[set] = []
    original_fit_and_evaluate = validation_module.fit_and_evaluate

    def spy(train_df, eval_df, config):
        assert set(train_df.index).isdisjoint(set(eval_df.index))
        seen_val_indices.append(set(eval_df.index))
        return original_fit_and_evaluate(train_df, eval_df, config)

    monkeypatch.setattr(validation_module, "fit_and_evaluate", spy)

    config = TrainingConfig(model_name="random_forest", model_params={"n_estimators": 5}, cv_folds=4)
    run_cross_validation(config, df=cv_df)

    # disjoint across folds, and their union covers every row exactly once
    assert len(seen_val_indices) == 4
    for i in range(len(seen_val_indices)):
        for j in range(i + 1, len(seen_val_indices)):
            assert seen_val_indices[i].isdisjoint(seen_val_indices[j])
    union = set().union(*seen_val_indices)
    assert union == set(cv_df.index)


def test_run_cross_validation_is_deterministic(cv_df):
    config = TrainingConfig(model_name="random_forest", model_params={"n_estimators": 5}, cv_folds=3)

    result_a = run_cross_validation(config, df=cv_df)
    result_b = run_cross_validation(config, df=cv_df)

    assert result_a.aggregated_metrics == result_b.aggregated_metrics


def test_run_cross_validation_supports_multiclass_label_column(cv_df):
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        cv_folds=2,
        label_column="attack_category",
    )

    result = run_cross_validation(config, df=cv_df)

    assert "precision_macro" in result.aggregated_metrics
    assert "precision_binary" not in result.aggregated_metrics


def test_run_cross_validation_raises_clear_error_when_folds_exceed_sample_count(cv_df):
    # only 20 rows in the fixture; StratifiedKFold cannot make 25 splits
    config = TrainingConfig(model_name="random_forest", model_params={"n_estimators": 5}, cv_folds=25)

    with pytest.raises(ValueError, match="cv_folds=25"):
        run_cross_validation(config, df=cv_df)


def test_run_cross_validation_raises_before_silently_degrading_stratification(cv_df):
    """sklearn's StratifiedKFold only *warns* (doesn't raise) when a class is
    rarer than cv_folds, then silently degrades stratification for it -- we
    must catch this ourselves rather than let it pass quietly."""
    # satan (probe) and guess_passwd (r2l) each have only 3 members
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        cv_folds=5,
        label_column="attack_category",
    )

    with pytest.raises(ValueError, match="cv_folds=5"):
        run_cross_validation(config, df=cv_df)


def test_run_cross_validation_uses_load_train_when_df_omitted(cv_df, monkeypatch):
    captured = {}

    def fake_load_train(full):
        captured["full"] = full
        return cv_df

    monkeypatch.setattr(validation_module, "load_train", fake_load_train)

    config = TrainingConfig(
        model_name="random_forest", model_params={"n_estimators": 5}, cv_folds=2, train_full=False
    )
    run_cross_validation(config)

    assert captured["full"] is False


def test_aggregate_fold_metrics_computes_mean_std_min_max():
    fold_metrics = [
        {"accuracy": 0.8, "roc_auc": 0.9, "confusion_matrix": [[1, 2], [3, 4]]},
        {"accuracy": 0.6, "roc_auc": 0.7, "confusion_matrix": [[2, 1], [1, 2]]},
    ]

    aggregated = _aggregate_fold_metrics(fold_metrics)

    assert aggregated["accuracy"]["mean"] == pytest.approx(0.7)
    assert aggregated["accuracy"]["min"] == pytest.approx(0.6)
    assert aggregated["accuracy"]["max"] == pytest.approx(0.8)
    assert aggregated["accuracy"]["std"] == pytest.approx(np.std([0.8, 0.6]))
    assert aggregated["accuracy"]["n_folds"] == 2
    assert "confusion_matrix" not in aggregated


def test_aggregate_fold_metrics_handles_metric_missing_from_some_folds():
    fold_metrics = [
        {"accuracy": 0.8, "roc_auc": 0.9},
        {"accuracy": 0.6},  # roc_auc omitted, e.g. a degenerate fold
    ]

    aggregated = _aggregate_fold_metrics(fold_metrics)

    assert aggregated["accuracy"]["n_folds"] == 2
    assert aggregated["roc_auc"]["n_folds"] == 1
    assert aggregated["roc_auc"]["mean"] == pytest.approx(0.9)
