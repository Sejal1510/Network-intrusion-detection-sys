import dataclasses
from pathlib import Path

import pytest

from nids.api.config import ServingConfig
from nids.api.inference import PredictionResult
from nids.api.model_loader import ServedEnsemble, ServedModel
from nids.api.pipeline import finish_record, process_record
from nids.api.schemas import PredictResponse
from nids.data import loader
from nids.data.schema import FEATURE_COLUMNS
from nids.training.config import TrainingConfig
from nids.training.core import fit_and_evaluate

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd.txt"


def _result_with_severity(severity: str) -> PredictionResult:
    return PredictionResult(
        prediction=1,
        probabilities={"0": 0.1, "1": 0.9},
        confidence=0.9,
        attack_category="dos",
        anomaly_score=None,
        is_anomaly=None,
        severity=severity,
    )


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
def served_ensemble(fixture_df):
    classifier = _build_served_model(fixture_df, "random_forest", n_estimators=5)
    return ServedEnsemble(classifier=classifier, anomaly_detector=None)


@pytest.fixture
def valid_record(fixture_df) -> dict:
    row = fixture_df.iloc[0].to_dict()
    return {k: row[k] for k in FEATURE_COLUMNS}


@pytest.fixture
def config():
    return ServingConfig(run_id="test-run", alert_threshold=0.0)  # every prediction alerts


def test_process_record_returns_predict_response_with_no_database(served_ensemble, valid_record, config):
    response = process_record(served_ensemble, valid_record, config=config, db_engine=None)

    assert isinstance(response, PredictResponse)
    assert response.risk_score is not None


def test_process_record_explain_false_leaves_explanation_none(served_ensemble, valid_record, config):
    response = process_record(
        served_ensemble, valid_record, config=config, db_engine=None, explain=False
    )
    assert response.explanation is None


def test_process_record_explain_true_populates_explanation(served_ensemble, valid_record, config):
    response = process_record(
        served_ensemble, valid_record, config=config, db_engine=None, explain=True
    )
    assert response.explanation is not None


def test_process_record_explain_callable_receives_prediction_and_risk_score(
    served_ensemble, valid_record, config
):
    seen = []

    def policy(result, risk_score):
        seen.append((result, risk_score))
        return False

    process_record(served_ensemble, valid_record, config=config, db_engine=None, explain=policy)

    assert len(seen) == 1
    result, risk_score = seen[0]
    assert result.prediction is not None
    assert risk_score.score >= 0.0


def test_process_record_explain_callable_true_only_when_alert_worthy(
    served_ensemble, valid_record, config
):
    """The live worker's actual policy: explain only flows that will
    raise an alert, not every flow."""

    def only_if_alert_worthy(result, risk_score):
        return risk_score.score >= config.alert_threshold

    response = process_record(
        served_ensemble, valid_record, config=config, db_engine=None, explain=only_if_alert_worthy
    )

    # config.alert_threshold=0.0 in this fixture -- every prediction is alert-worthy
    assert response.explanation is not None
    assert response.alert_id is not None


def test_process_record_raises_valueerror_for_invalid_record(served_ensemble, config):
    with pytest.raises(ValueError, match="missing required raw feature column"):
        process_record(served_ensemble, {"duration": 0}, config=config, db_engine=None)


def test_process_record_persist_false_skips_persistence_even_with_db_configured(
    served_ensemble, valid_record, tmp_path
):
    from nids.api import store

    engine = store.create_db_engine(f"sqlite:///{tmp_path / 'test.db'}")
    cfg = ServingConfig(run_id="test-run", alert_threshold=0.0, database_url=str(engine.url))

    process_record(served_ensemble, valid_record, config=cfg, db_engine=engine, persist=False)

    assert store.list_predictions(engine).total == 0


def test_finish_record_matches_process_record_when_given_the_same_prediction(
    served_ensemble, valid_record, config
):
    from nids.api.inference import predict_one

    result = predict_one(served_ensemble, valid_record)

    via_finish = finish_record(
        served_ensemble, result, valid_record, None, config=config, db_engine=None
    )
    via_process = process_record(served_ensemble, valid_record, config=config, db_engine=None)

    assert via_finish.prediction == via_process.prediction
    assert via_finish.risk_score.score == via_process.risk_score.score


def test_finish_record_calls_notify_when_alert_meets_min_severity(served_ensemble, valid_record, config):
    notified = []
    result = _result_with_severity("critical")

    finish_record(
        served_ensemble, result, valid_record, None, config=config, db_engine=None,
        notify=notified.append,
    )

    assert len(notified) == 1
    assert notified[0].level == "critical"


def test_finish_record_skips_notify_when_below_min_severity(served_ensemble, valid_record, config):
    strict_config = dataclasses.replace(config, notification_min_severity="critical")
    notified = []
    result = _result_with_severity("high")

    finish_record(
        served_ensemble, result, valid_record, None, config=strict_config, db_engine=None,
        notify=notified.append,
    )

    assert notified == []


def test_finish_record_skips_notify_when_no_alert_generated(served_ensemble, valid_record):
    no_alert_config = ServingConfig(run_id="test-run", alert_threshold=1000.0)
    notified = []
    result = _result_with_severity("low")

    finish_record(
        served_ensemble, result, valid_record, None, config=no_alert_config, db_engine=None,
        notify=notified.append,
    )

    assert notified == []


def test_process_record_forwards_notify_to_finish_record(served_ensemble, valid_record, config):
    notified = []

    process_record(served_ensemble, valid_record, config=config, db_engine=None, notify=notified.append)

    assert len(notified) == 1
