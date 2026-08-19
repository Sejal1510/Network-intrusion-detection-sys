from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nids.api import store
from nids.api.app import create_app
from nids.api.config import ServingConfig
from nids.api.inference import PredictionResult
from nids.api.risk import RiskScore
from nids.api.threat_intel import EnrichmentResult
from nids.api.user_auth import create_session, register_user
from nids.data import loader
from nids.training.config import TrainingConfig
from nids.training.run import run_training

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd.txt"


@pytest.fixture
def fixture_df():
    return loader._read_nsl_kdd_file(FIXTURE)


@pytest.fixture
def app(fixture_df, tmp_path):
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        artifact_root=tmp_path / "runs",
        run_name="enrichment-fixture-run",
    )
    run_training(config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)
    return create_app(
        ServingConfig(
            run_id="enrichment-fixture-run",
            artifact_root=tmp_path / "runs",
            database_url=f"sqlite:///{tmp_path / 'history.db'}",
        )
    )


@pytest.fixture
def client(app):
    test_client = TestClient(app)
    user = register_user(app.state.db_engine, "analyst1", "hunter2", "analyst")
    session = create_session(app.state.db_engine, user.id, ttl_seconds=3600)
    test_client.headers.update({"Authorization": f"Bearer {session.token}"})
    return test_client


def _save_prediction(engine, *, src_ip=None, dst_ip=None) -> str:
    result = PredictionResult(
        prediction="dos",
        probabilities=None,
        confidence=0.9,
        attack_category="dos",
        anomaly_score=None,
        is_anomaly=None,
        severity="high",
    )
    risk_score = RiskScore(score=80.0, severity="high", factors={"attack_confidence": 0.8})
    return store.save_prediction(
        engine,
        result,
        risk_score,
        mitre=None,
        raw_record={"src_ip": src_ip, "dst_ip": dst_ip} if src_ip or dst_ip else {},
        run_id="enrichment-fixture-run",
        label_column="attack_category",
        source="agent",
        src_ip=src_ip,
        dst_ip=dst_ip,
    )


def _enrichment(indicator: str, provider: str, verdict: str = "malicious") -> EnrichmentResult:
    return EnrichmentResult(
        indicator=indicator,
        provider=provider,
        verdict=verdict,
        confidence=90.0,
        raw_response={"x": 1},
        looked_up_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


# --- GET /history/predictions/{id}/enrichment ---------------------------------


def test_prediction_enrichment_404s_for_unknown_prediction(client):
    response = client.get("/history/predictions/does-not-exist/enrichment")
    assert response.status_code == 404


def test_prediction_enrichment_requires_authentication(app):
    prediction_id = _save_prediction(app.state.db_engine, src_ip="8.8.8.8")
    response = TestClient(app).get(f"/history/predictions/{prediction_id}/enrichment")
    assert response.status_code == 401


def test_prediction_enrichment_empty_list_when_api_sourced_with_no_ip(client, app):
    """The honest, expected case for /predict-sourced predictions --
    NSL-KDD has no IP field, so there's nothing to enrich, ever."""
    prediction_id = _save_prediction(app.state.db_engine)
    response = client.get(f"/history/predictions/{prediction_id}/enrichment")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_prediction_enrichment_empty_list_when_not_yet_enriched(client, app):
    """Has routable indicators, but the async dispatcher hasn't produced
    a result yet -- still a normal 200, not an error."""
    prediction_id = _save_prediction(app.state.db_engine, src_ip="8.8.8.8", dst_ip="9.9.9.9")
    response = client.get(f"/history/predictions/{prediction_id}/enrichment")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_prediction_enrichment_returns_cached_results_with_correct_roles(client, app):
    engine = app.state.db_engine
    prediction_id = _save_prediction(engine, src_ip="8.8.8.8", dst_ip="9.9.9.9")
    store.upsert_enrichment(engine, _enrichment("8.8.8.8", "abuseipdb", "malicious"), ttl_seconds=3600)
    store.upsert_enrichment(engine, _enrichment("9.9.9.9", "greynoise", "benign"), ttl_seconds=3600)

    response = client.get(f"/history/predictions/{prediction_id}/enrichment")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    by_indicator = {item["indicator"]: item for item in items}
    assert by_indicator["8.8.8.8"]["indicator_role"] == "src"
    assert by_indicator["8.8.8.8"]["provider"] == "abuseipdb"
    assert by_indicator["8.8.8.8"]["verdict"] == "malicious"
    assert by_indicator["9.9.9.9"]["indicator_role"] == "dst"
    assert by_indicator["9.9.9.9"]["verdict"] == "benign"


def test_prediction_enrichment_does_not_leak_unrelated_indicators(client, app):
    """A cached result for some other IP entirely (never seen by this
    prediction) must never show up on it."""
    engine = app.state.db_engine
    prediction_id = _save_prediction(engine, src_ip="8.8.8.8")
    store.upsert_enrichment(engine, _enrichment("1.1.1.1", "abuseipdb"), ttl_seconds=3600)

    response = client.get(f"/history/predictions/{prediction_id}/enrichment")

    assert response.json()["items"] == []


# --- GET /history/alerts/{id}/enrichment ---------------------------------------


def test_alert_enrichment_404s_for_unknown_alert(client):
    response = client.get("/history/alerts/does-not-exist/enrichment")
    assert response.status_code == 404


def test_alert_enrichment_resolves_through_its_prediction(client, app):
    from nids.api.alerts import Alert

    engine = app.state.db_engine
    prediction_id = _save_prediction(engine, src_ip="8.8.8.8")
    store.upsert_enrichment(engine, _enrichment("8.8.8.8", "abuseipdb", "malicious"), ttl_seconds=3600)
    alert = Alert(
        alert_id="alert-1",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        level="high",
        title="Test alert",
        message="test",
        risk_score=80.0,
        attack_category="dos",
        mitre=None,
        source="ml",
    )
    store.save_alert(engine, prediction_id, alert)

    response = client.get("/history/alerts/alert-1/enrichment")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["indicator"] == "8.8.8.8"
    assert items[0]["indicator_role"] == "src"
