from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from nids.api import store
from nids.api.alerts import Alert
from nids.api.explain import Explanation, FeatureContribution
from nids.api.inference import PredictionResult
from nids.api.mitre import MitreMapping, MitreTechnique
from nids.api.risk import RiskScore


@pytest.fixture
def engine(tmp_path):
    return store.create_db_engine(f"sqlite:///{tmp_path / 'test.db'}")


def _result(prediction=1, attack_category=None, severity="critical") -> PredictionResult:
    return PredictionResult(
        prediction=prediction,
        probabilities={"0": 0.1, "1": 0.9},
        confidence=0.9,
        attack_category=attack_category,
        anomaly_score=0.8,
        is_anomaly=True,
        severity=severity,
    )


def _risk(score=90.0, severity="critical") -> RiskScore:
    return RiskScore(
        score=score, severity=severity, factors={"attack_confidence": 0.5, "severity_band": 0.2}
    )


def _alert(alert_id="alert-1", level="critical", risk_score=90.0) -> Alert:
    return Alert(
        alert_id=alert_id,
        created_at=datetime.now(timezone.utc),
        level=level,
        title="Critical risk detected",
        message="CRITICAL risk detected (score 90/100)",
        risk_score=risk_score,
        attack_category=None,
        mitre=None,
        source="api",
    )


def test_save_and_get_prediction_roundtrips(engine):
    prediction_id = store.save_prediction(
        engine,
        _result(),
        _risk(),
        mitre=None,
        raw_record={"duration": 0},
        run_id="run-1",
        label_column="is_attack",
    )

    fetched = store.get_prediction(engine, prediction_id)

    assert fetched is not None
    assert fetched.id == prediction_id
    assert fetched.run_id == "run-1"
    assert fetched.severity == "critical"
    assert fetched.risk_score == 90.0
    assert fetched.raw_record == {"duration": 0}
    assert fetched.explanation is None


def test_get_prediction_returns_none_for_unknown_id(engine):
    assert store.get_prediction(engine, "does-not-exist") is None


def test_save_prediction_with_explanation_roundtrips(engine):
    explanation = Explanation(
        base_value=0.1,
        top_features=[
            FeatureContribution(feature="service", value="http", contribution=0.5, direction="positive")
        ],
        summary="Predicted 1 primarily due to: service='http' (+0.50).",
    )
    prediction_id = store.save_prediction(
        engine,
        _result(),
        _risk(),
        mitre=None,
        raw_record={},
        run_id="run-1",
        label_column="is_attack",
        explanation=explanation,
    )

    fetched = store.get_prediction(engine, prediction_id)

    assert fetched.explanation is not None
    assert fetched.explanation.summary == explanation.summary
    assert fetched.explanation.top_features[0]["feature"] == "service"


def test_save_prediction_with_mitre_mapping_roundtrips(engine):
    mapping = MitreMapping(
        tactic="Impact",
        techniques=[MitreTechnique(id="T1498", name="Network DoS", url="https://example.com")],
    )
    prediction_id = store.save_prediction(
        engine,
        _result(attack_category="dos"),
        _risk(),
        mitre=mapping,
        raw_record={},
        run_id="run-1",
        label_column="attack_category",
    )

    fetched = store.get_prediction(engine, prediction_id)

    assert fetched.mitre["tactic"] == "Impact"
    assert fetched.mitre["techniques"][0]["id"] == "T1498"


def test_save_and_get_alert_roundtrips(engine):
    prediction_id = store.save_prediction(
        engine, _result(), _risk(), mitre=None, raw_record={}, run_id="run-1", label_column="is_attack"
    )
    alert_id = store.save_alert(engine, prediction_id, _alert())

    fetched = store.get_alert(engine, alert_id)

    assert fetched is not None
    assert fetched.id == "alert-1"
    assert fetched.prediction_id == prediction_id
    assert fetched.acknowledged is False


def test_get_alert_returns_none_for_unknown_id(engine):
    assert store.get_alert(engine, "does-not-exist") is None


def test_acknowledge_alert_flips_flag_and_is_idempotent(engine):
    prediction_id = store.save_prediction(
        engine, _result(), _risk(), mitre=None, raw_record={}, run_id="run-1", label_column="is_attack"
    )
    store.save_alert(engine, prediction_id, _alert())

    first = store.acknowledge_alert(engine, "alert-1")
    second = store.acknowledge_alert(engine, "alert-1")

    assert first.acknowledged is True
    assert second.acknowledged is True


def test_acknowledge_alert_returns_none_for_unknown_id(engine):
    assert store.acknowledge_alert(engine, "does-not-exist") is None


def test_list_predictions_filters_by_severity(engine):
    for severity in ["critical", "low", "critical"]:
        store.save_prediction(
            engine,
            _result(severity=severity),
            _risk(severity=severity),
            mitre=None,
            raw_record={},
            run_id="run-1",
            label_column="is_attack",
        )

    page = store.list_predictions(engine, severity="critical")

    assert page.total == 2
    assert all(item.severity == "critical" for item in page.items)


def test_list_predictions_filters_by_min_risk_score(engine):
    store.save_prediction(
        engine, _result(), _risk(score=90.0), mitre=None, raw_record={}, run_id="run-1", label_column="is_attack"
    )
    store.save_prediction(
        engine, _result(), _risk(score=10.0), mitre=None, raw_record={}, run_id="run-1", label_column="is_attack"
    )

    page = store.list_predictions(engine, min_risk_score=50.0)

    assert page.total == 1
    assert page.items[0].risk_score == 90.0


def test_list_predictions_pagination_disjoint_pages(engine):
    for _ in range(5):
        store.save_prediction(
            engine, _result(), _risk(), mitre=None, raw_record={}, run_id="run-1", label_column="is_attack"
        )

    page_one = store.list_predictions(engine, limit=2, offset=0)
    page_two = store.list_predictions(engine, limit=2, offset=2)

    assert page_one.total == 5
    assert len(page_one.items) == 2
    assert len(page_two.items) == 2
    assert {i.id for i in page_one.items}.isdisjoint({i.id for i in page_two.items})


def test_list_predictions_orders_newest_first(engine):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with Session(engine) as session:
        for i in range(3):
            session.add(
                store.PredictionRecord(
                    run_id="run-1",
                    label_column="is_attack",
                    prediction="1",
                    severity="low",
                    risk_score=0.0,
                    risk_factors={},
                    raw_record={},
                    created_at=base + timedelta(minutes=i),
                )
            )
        session.commit()

    page = store.list_predictions(engine)

    timestamps = [item.created_at for item in page.items]
    assert timestamps == sorted(timestamps, reverse=True)


def test_list_predictions_filters_by_date_range(engine):
    store.save_prediction(
        engine, _result(), _risk(), mitre=None, raw_record={}, run_id="run-1", label_column="is_attack"
    )

    future_start = datetime.now(timezone.utc) + timedelta(days=1)
    page = store.list_predictions(engine, start_date=future_start)

    assert page.total == 0


def test_list_alerts_filters_by_acknowledged(engine):
    prediction_id = store.save_prediction(
        engine, _result(), _risk(), mitre=None, raw_record={}, run_id="run-1", label_column="is_attack"
    )
    store.save_alert(engine, prediction_id, _alert(alert_id="a1"))
    store.save_alert(engine, prediction_id, _alert(alert_id="a2", level="high", risk_score=80.0))
    store.acknowledge_alert(engine, "a1")

    unacknowledged = store.list_alerts(engine, acknowledged=False)

    assert unacknowledged.total == 1
    assert unacknowledged.items[0].id == "a2"


def test_list_alerts_filters_by_level(engine):
    prediction_id = store.save_prediction(
        engine, _result(), _risk(), mitre=None, raw_record={}, run_id="run-1", label_column="is_attack"
    )
    store.save_alert(engine, prediction_id, _alert(alert_id="a1", level="critical"))
    store.save_alert(engine, prediction_id, _alert(alert_id="a2", level="high"))

    page = store.list_alerts(engine, level="high")

    assert page.total == 1
    assert page.items[0].id == "a2"


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------


def test_register_device_roundtrips(engine):
    device = store.register_device(engine, name="ayush-laptop", credential_hash="hash1")

    assert device.name == "ayush-laptop"
    assert device.revoked is False
    assert device.last_seen_at is None


def test_get_device_by_credential_hash_finds_registered_device(engine):
    registered = store.register_device(engine, name="ayush-laptop", credential_hash="hash1")

    found = store.get_device_by_credential_hash(engine, "hash1")

    assert found is not None
    assert found.id == registered.id


def test_get_device_by_credential_hash_returns_none_for_unknown_hash(engine):
    assert store.get_device_by_credential_hash(engine, "not-a-real-hash") is None


def test_touch_device_last_seen_sets_timestamp(engine):
    device = store.register_device(engine, name="ayush-laptop", credential_hash="hash1")

    store.touch_device_last_seen(engine, device.id)

    refreshed = store.get_device_by_credential_hash(engine, "hash1")
    assert refreshed.last_seen_at is not None


def test_revoke_device_sets_revoked_flag(engine):
    device = store.register_device(engine, name="ayush-laptop", credential_hash="hash1")

    revoked = store.revoke_device(engine, device.id)

    assert revoked.revoked is True
    assert store.get_device_by_credential_hash(engine, "hash1").revoked is True


def test_revoke_device_returns_none_for_unknown_id(engine):
    assert store.revoke_device(engine, "does-not-exist") is None


# ---------------------------------------------------------------------------
# device_id tagging on predictions/alerts (live capture agent flows)
# ---------------------------------------------------------------------------


def test_save_prediction_persists_device_id(engine):
    prediction_id = store.save_prediction(
        engine,
        _result(),
        _risk(),
        mitre=None,
        raw_record={},
        run_id="run-1",
        label_column="is_attack",
        device_id="device-1",
    )

    assert store.get_prediction(engine, prediction_id).device_id == "device-1"


def test_save_alert_persists_device_id(engine):
    prediction_id = store.save_prediction(
        engine, _result(), _risk(), mitre=None, raw_record={}, run_id="run-1", label_column="is_attack"
    )
    alert_id = store.save_alert(engine, prediction_id, _alert(), device_id="device-1")

    assert store.get_alert(engine, alert_id).device_id == "device-1"


def test_list_predictions_filters_by_device_id(engine):
    store.save_prediction(
        engine, _result(), _risk(), mitre=None, raw_record={}, run_id="run-1",
        label_column="is_attack", device_id="device-1",
    )
    store.save_prediction(
        engine, _result(), _risk(), mitre=None, raw_record={}, run_id="run-1",
        label_column="is_attack", device_id="device-2",
    )

    page = store.list_predictions(engine, device_id="device-1")

    assert page.total == 1
    assert page.items[0].device_id == "device-1"


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


def test_record_and_list_audit_event_roundtrips(engine):
    event = store.record_audit_event(engine, event_type="device_paired", actor="127.0.0.1")

    page = store.list_audit_events(engine)

    assert page.total == 1
    assert page.items[0].id == event.id
    assert page.items[0].event_type == "device_paired"
    assert page.items[0].actor == "127.0.0.1"
    assert page.items[0].target_id is None
    assert page.items[0].detail is None


def test_record_audit_event_with_target_id_and_detail_roundtrips(engine):
    event = store.record_audit_event(
        engine,
        event_type="alert_acknowledged",
        actor="10.0.0.5",
        target_id="alert-1",
        detail="acknowledged via /history/alerts/alert-1/acknowledge",
    )

    page = store.list_audit_events(engine)

    assert page.items[0].id == event.id
    assert page.items[0].target_id == "alert-1"
    assert page.items[0].detail == "acknowledged via /history/alerts/alert-1/acknowledge"


def test_list_audit_events_filters_by_event_type(engine):
    store.record_audit_event(engine, event_type="device_paired", actor="127.0.0.1")
    store.record_audit_event(engine, event_type="device_pair_failed", actor="127.0.0.1")

    page = store.list_audit_events(engine, event_type="device_pair_failed")

    assert page.total == 1
    assert page.items[0].event_type == "device_pair_failed"


def test_list_audit_events_filters_by_actor(engine):
    store.record_audit_event(engine, event_type="device_paired", actor="1.1.1.1")
    store.record_audit_event(engine, event_type="device_paired", actor="2.2.2.2")

    page = store.list_audit_events(engine, actor="2.2.2.2")

    assert page.total == 1
    assert page.items[0].actor == "2.2.2.2"


def test_list_audit_events_paginates(engine):
    for i in range(5):
        store.record_audit_event(engine, event_type="device_paired", actor=f"10.0.0.{i}")

    page_one = store.list_audit_events(engine, limit=2, offset=0)
    page_two = store.list_audit_events(engine, limit=2, offset=2)

    assert page_one.total == 5
    assert len(page_one.items) == 2
    assert len(page_two.items) == 2
    assert {i.id for i in page_one.items}.isdisjoint({i.id for i in page_two.items})


def test_list_audit_events_empty_returns_empty_page(engine):
    page = store.list_audit_events(engine)

    assert page.total == 0
    assert page.items == []
