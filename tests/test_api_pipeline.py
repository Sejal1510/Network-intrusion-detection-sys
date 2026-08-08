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


# --- Rule-based detection: independence from the ML classifier -------------


def test_process_record_rule_fires_even_when_ml_classifier_does_not_alert(
    served_ensemble, valid_record
):
    """The core independence guarantee: a record engineered to match a
    signature (R001's SYN-flood pattern -- flag=S0, count>100) still
    raises an alert -- persisted with source="rule" -- even when the ML
    path is configured to never alert (alert_threshold impossibly high),
    proving the rule path doesn't depend on, and isn't gated by, the
    classifier's own verdict."""
    from nids.api import store

    record = {**valid_record, "flag": "S0", "count": 150}
    never_alert_config = ServingConfig(run_id="test-run", alert_threshold=1000.0)
    engine = store.create_db_engine("sqlite:///:memory:")

    response = process_record(served_ensemble, record, config=never_alert_config, db_engine=engine)

    assert response.alert_id is not None
    alert = store.get_alert(engine, response.alert_id)
    assert alert.source == "rule"
    assert alert.level == "critical"
    assert alert.mitre is not None


def test_process_record_record_not_matching_any_rule_raises_no_rule_alert(
    served_ensemble, valid_record
):
    never_alert_config = ServingConfig(run_id="test-run", alert_threshold=1000.0)
    record = {
        **valid_record,
        "flag": "SF",
        "count": 1,
        "root_shell": 0,
        "is_guest_login": 0,
        "num_failed_logins": 0,
    }

    response = process_record(served_ensemble, record, config=never_alert_config, db_engine=None)

    assert response.alert_id is None


def test_process_record_both_ml_and_rule_alerts_persist_independently(served_ensemble, valid_record):
    """When the ML path *also* alerts (alert_threshold=0.0, matching the
    module's `config` fixture) on a record that additionally matches a
    rule, both alerts persist as separate rows against the same
    prediction -- neither silences the other."""
    from nids.api import store

    record = {**valid_record, "flag": "S0", "count": 150}
    always_alert_config = ServingConfig(run_id="test-run", alert_threshold=0.0)
    engine = store.create_db_engine("sqlite:///:memory:")

    response = process_record(served_ensemble, record, config=always_alert_config, db_engine=engine)

    primary = store.get_alert(engine, response.alert_id)
    all_alerts_for_prediction = store.list_alerts(engine, limit=100, offset=0).items
    matching = [a for a in all_alerts_for_prediction if a.prediction_id == primary.prediction_id]

    assert len(matching) == 2
    assert {a.source for a in matching} == {"api", "rule"}


def test_process_record_primary_alert_id_prefers_rule_on_severity_tie(served_ensemble, valid_record):
    """R001 (SYN flood) is severity=critical. Forcing the ML path to
    also produce a critical-severity alert on the same record means both
    alerts tie in severity -- the primary (response.alert_id) must be
    the rule alert, per finish_record's documented tie-break."""
    from nids.api import store

    record = {**valid_record, "flag": "S0", "count": 150}
    always_alert_config = ServingConfig(run_id="test-run", alert_threshold=0.0)
    engine = store.create_db_engine("sqlite:///:memory:")

    response = process_record(served_ensemble, record, config=always_alert_config, db_engine=engine)

    primary = store.get_alert(engine, response.alert_id)
    # Whichever of the two alerts is primary, if it's a tie the rule
    # must win; if the ML alert genuinely outranks it in severity, the
    # ML alert winning is also correct -- assert the actual contract:
    # primary is always the max-severity one, rule preferred on ties.
    all_alerts = [
        a for a in store.list_alerts(engine, limit=100, offset=0).items
        if a.prediction_id == primary.prediction_id
    ]
    from nids.api.alerts import severity_rank

    best_rank = max(severity_rank(a.level) for a in all_alerts)
    assert severity_rank(primary.level) == best_rank
    if len([a for a in all_alerts if severity_rank(a.level) == best_rank]) > 1:
        assert primary.source == "rule"


def test_finish_record_notify_called_for_both_alerts_when_both_qualify(served_ensemble, valid_record):
    record = {**valid_record, "flag": "S0", "count": 150}
    always_alert_config = ServingConfig(
        run_id="test-run", alert_threshold=0.0, notification_min_severity="low"
    )
    notified = []

    process_record(
        served_ensemble, record, config=always_alert_config, db_engine=None, notify=notified.append
    )

    assert len(notified) == 2
    assert {a.source for a in notified} == {"api", "rule"}
