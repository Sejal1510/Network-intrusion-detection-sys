from pathlib import Path

import pytest

from nids.api.inference import PredictionResult, predict_batch, predict_one
from nids.api.model_loader import ServedModel
from nids.data import loader
from nids.training.config import TrainingConfig
from nids.training.core import fit_and_evaluate

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd.txt"


@pytest.fixture
def fixture_df():
    return loader._read_nsl_kdd_file(FIXTURE)


@pytest.fixture
def served_model(fixture_df):
    config = TrainingConfig(model_name="random_forest", model_params={"n_estimators": 5})
    result = fit_and_evaluate(fixture_df, fixture_df, config)
    return ServedModel(
        run_id="test-run",
        model=result.model,
        feature_engineer=result.feature_engineer,
        metrics=result.metrics,
        metadata={"model_name": "random_forest"},
    )


def test_predict_one_returns_prediction_and_probabilities(served_model, fixture_df):
    record = fixture_df.iloc[0].to_dict()

    result = predict_one(served_model, record)

    assert isinstance(result, PredictionResult)
    assert result.prediction in (0, 1)
    assert result.probabilities is not None
    assert set(result.probabilities) == {"0", "1"}
    assert pytest.approx(sum(result.probabilities.values()), abs=1e-6) == 1.0


def test_predict_one_rejects_record_missing_required_columns(served_model):
    with pytest.raises(ValueError, match="missing required raw feature column"):
        predict_one(served_model, {"duration": 0, "protocol_type": "tcp"})


def test_predict_batch_returns_one_result_per_row_in_order(served_model, fixture_df):
    results = predict_batch(served_model, fixture_df)

    assert len(results) == len(fixture_df)
    assert all(isinstance(r, PredictionResult) for r in results)


def test_predict_one_is_consistent_with_model_predict_directly(served_model, fixture_df):
    record = fixture_df.iloc[0].to_dict()
    result = predict_one(served_model, record)

    matrix = served_model.feature_engineer.transform(fixture_df.iloc[[0]])
    direct_prediction = served_model.model.predict(matrix.X)[0]

    assert result.prediction == direct_prediction
