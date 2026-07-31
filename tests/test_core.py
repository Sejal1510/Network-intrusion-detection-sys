from pathlib import Path

import numpy as np
import pytest
from catboost import CatBoostClassifier
from sklearn.ensemble import RandomForestClassifier

from nids.data import loader
from nids.training.config import TrainingConfig
from nids.training.core import FitEvalResult, fit_and_evaluate

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd.txt"


@pytest.fixture
def fixture_df():
    return loader._read_nsl_kdd_file(FIXTURE)


def test_fit_and_evaluate_returns_fitted_components(fixture_df):
    config = TrainingConfig(model_name="random_forest", model_params={"n_estimators": 5})

    result = fit_and_evaluate(fixture_df, fixture_df, config)

    assert isinstance(result, FitEvalResult)
    assert result.feature_engineer.is_fitted
    assert isinstance(result.model, RandomForestClassifier)
    assert "accuracy" in result.metrics


def test_fit_and_evaluate_fits_feature_engineer_on_train_split_only(fixture_df):
    """The core leakage-prevention guarantee: with disjoint train/eval
    splits, the fitted FeatureEngineer must have seen only the train rows."""
    train_df = fixture_df.iloc[:2]
    eval_df = fixture_df.iloc[2:]
    config = TrainingConfig(model_name="random_forest", model_params={"n_estimators": 5})

    result = fit_and_evaluate(train_df, eval_df, config)

    assert result.feature_engineer.fit_metadata["n_samples_fit"] == len(train_df)
    assert result.metrics["n_samples"] == len(eval_df)


def test_fit_and_evaluate_respects_model_name_in_config(fixture_df):
    config = TrainingConfig(model_name="catboost", model_params={"iterations": 5, "depth": 2})

    result = fit_and_evaluate(fixture_df, fixture_df, config)

    assert isinstance(result.model, CatBoostClassifier)


def test_fit_and_evaluate_supports_multiclass_label_column(fixture_df):
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        label_column="attack_category",
    )

    result = fit_and_evaluate(fixture_df, fixture_df, config)

    assert "precision_macro" in result.metrics
    assert "precision_binary" not in result.metrics


def test_fit_and_evaluate_is_deterministic_given_same_seed(fixture_df):
    config = TrainingConfig(model_name="random_forest", model_params={"n_estimators": 5})

    result_a = fit_and_evaluate(fixture_df, fixture_df, config)
    result_b = fit_and_evaluate(fixture_df, fixture_df, config)

    np.testing.assert_array_equal(
        result_a.model.predict(result_a.feature_engineer.transform(fixture_df).X),
        result_b.model.predict(result_b.feature_engineer.transform(fixture_df).X),
    )
    assert result_a.metrics["accuracy"] == result_b.metrics["accuracy"]
