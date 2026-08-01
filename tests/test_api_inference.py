from pathlib import Path

import pytest

from nids.api.inference import PredictionResult, predict_batch, predict_one
from nids.api.model_loader import ServedEnsemble, ServedModel
from nids.data import loader
from nids.training.config import TrainingConfig
from nids.training.core import fit_and_evaluate

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd.txt"

SEVERITY_LEVELS = {"critical", "high", "medium", "low"}


@pytest.fixture
def fixture_df():
    return loader._read_nsl_kdd_file(FIXTURE)


def _build_served_model(fixture_df, model_name, label_column="is_attack", **model_params):
    config = TrainingConfig(model_name=model_name, label_column=label_column, model_params=model_params)
    result = fit_and_evaluate(fixture_df, fixture_df, config)
    return ServedModel(
        run_id=f"test-{model_name}",
        model=result.model,
        feature_engineer=result.feature_engineer,
        metrics=result.metrics,
        metadata={"model_name": model_name, "label_column": label_column},
    )


@pytest.fixture
def classifier(fixture_df):
    return _build_served_model(fixture_df, "random_forest", n_estimators=5)


@pytest.fixture
def anomaly_detector(fixture_df):
    return _build_served_model(fixture_df, "isolation_forest")


@pytest.fixture
def served_ensemble(classifier):
    """Classifier-only -- reproduces Milestone 2 serving exactly."""
    return ServedEnsemble(classifier=classifier, anomaly_detector=None)


@pytest.fixture
def hybrid_ensemble(classifier, anomaly_detector):
    return ServedEnsemble(classifier=classifier, anomaly_detector=anomaly_detector)


def test_predict_one_returns_prediction_and_probabilities(served_ensemble, fixture_df):
    record = fixture_df.iloc[0].to_dict()

    result = predict_one(served_ensemble, record)

    assert isinstance(result, PredictionResult)
    assert result.prediction in (0, 1)
    assert result.probabilities is not None
    assert set(result.probabilities) == {"0", "1"}
    assert pytest.approx(sum(result.probabilities.values()), abs=1e-6) == 1.0
    assert result.confidence == max(result.probabilities.values())


def test_predict_one_rejects_record_missing_required_columns(served_ensemble):
    with pytest.raises(ValueError, match="missing required raw feature column"):
        predict_one(served_ensemble, {"duration": 0, "protocol_type": "tcp"})


def test_predict_batch_returns_one_result_per_row_in_order(served_ensemble, fixture_df):
    results = predict_batch(served_ensemble, fixture_df)

    assert len(results) == len(fixture_df)
    assert all(isinstance(r, PredictionResult) for r in results)


def test_predict_one_is_consistent_with_model_predict_directly(served_ensemble, fixture_df):
    record = fixture_df.iloc[0].to_dict()
    result = predict_one(served_ensemble, record)

    matrix = served_ensemble.classifier.feature_engineer.transform(fixture_df.iloc[[0]])
    direct_prediction = served_ensemble.classifier.model.predict(matrix.X)[0]

    assert result.prediction == direct_prediction


def test_classifier_only_leaves_anomaly_fields_none(served_ensemble, fixture_df):
    """Milestone 2 regression: with no anomaly detector served, the hybrid
    fields must be None and everything else behaves exactly as before."""
    record = fixture_df.iloc[0].to_dict()

    result = predict_one(served_ensemble, record)

    assert result.anomaly_score is None
    assert result.is_anomaly is None
    assert result.severity in SEVERITY_LEVELS


def test_classifier_only_attack_category_is_none_for_is_attack_label(served_ensemble, fixture_df):
    record = fixture_df.iloc[0].to_dict()

    result = predict_one(served_ensemble, record)

    assert result.attack_category is None


def test_predict_one_with_anomaly_detector_populates_hybrid_fields(hybrid_ensemble, fixture_df):
    record = fixture_df.iloc[0].to_dict()

    result = predict_one(hybrid_ensemble, record)

    assert result.anomaly_score is not None
    assert 0.0 <= result.anomaly_score <= 1.0
    assert isinstance(result.is_anomaly, bool)
    assert result.severity in SEVERITY_LEVELS


def test_predict_batch_with_anomaly_detector_populates_hybrid_fields(hybrid_ensemble, fixture_df):
    results = predict_batch(hybrid_ensemble, fixture_df)

    assert len(results) == len(fixture_df)
    assert all(r.anomaly_score is not None for r in results)
    assert all(isinstance(r.is_anomaly, bool) for r in results)


def test_attack_category_populated_for_attack_category_label_column(fixture_df):
    classifier = _build_served_model(
        fixture_df, "random_forest", label_column="attack_category", n_estimators=5
    )
    ensemble = ServedEnsemble(classifier=classifier, anomaly_detector=None)
    record = fixture_df.iloc[0].to_dict()

    result = predict_one(ensemble, record)

    assert isinstance(result.prediction, str)
    assert result.attack_category == result.prediction
