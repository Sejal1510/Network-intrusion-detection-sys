import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nids.api.app import create_app
from nids.api.config import ServingConfig
from nids.data import loader
from nids.data.schema import FEATURE_COLUMNS
from nids.training.config import TrainingConfig
from nids.training.run import run_training

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd.txt"


@pytest.fixture
def fixture_df():
    return loader._read_nsl_kdd_file(FIXTURE)


@pytest.fixture
def valid_record(fixture_df) -> dict:
    record = fixture_df.iloc[0].to_dict()
    return {k: record[k] for k in FEATURE_COLUMNS}


@pytest.fixture
def client_without_db(fixture_df, tmp_path):
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        artifact_root=tmp_path / "runs",
        run_name="history-fixture-run",
    )
    run_training(config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)

    app = create_app(ServingConfig(run_id="history-fixture-run", artifact_root=tmp_path / "runs"))
    return TestClient(app)


@pytest.fixture
def client(fixture_df, tmp_path):
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        artifact_root=tmp_path / "runs",
        run_name="history-fixture-run",
    )
    run_training(config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)

    app = create_app(
        ServingConfig(
            run_id="history-fixture-run",
            artifact_root=tmp_path / "runs",
            database_url=f"sqlite:///{tmp_path / 'history.db'}",
            alert_threshold=0.0,  # every prediction raises an alert, for easy testing
        )
    )
    return TestClient(app)


def test_history_predictions_503s_without_database(client_without_db, valid_record):
    response = client_without_db.get("/history/predictions")
    assert response.status_code == 503


def test_history_alerts_503s_without_database(client_without_db):
    response = client_without_db.get("/history/alerts")
    assert response.status_code == 503


def test_list_predictions_empty_initially(client):
    response = client.get("/history/predictions")

    assert response.status_code == 200
    body = response.json()
    assert body == {"items": [], "total": 0, "limit": 20, "offset": 0}


def test_predict_then_list_predictions_finds_it(client, valid_record):
    predict_response = client.post("/predict", json=valid_record)
    prediction_prediction = predict_response.json()["prediction"]

    history = client.get("/history/predictions").json()

    assert history["total"] == 1
    assert history["items"][0]["prediction"] == str(prediction_prediction)
    assert history["items"][0]["raw_record"]["service"] == valid_record["service"]


def test_get_prediction_by_id(client, valid_record):
    client.post("/predict", json=valid_record)
    prediction_id = client.get("/history/predictions").json()["items"][0]["id"]

    response = client.get(f"/history/predictions/{prediction_id}")

    assert response.status_code == 200
    assert response.json()["id"] == prediction_id


def test_get_prediction_404s_for_unknown_id(client):
    response = client.get("/history/predictions/does-not-exist")
    assert response.status_code == 404


def test_get_prediction_with_explanation_included(client, valid_record):
    client.post("/predict?explain=true", json=valid_record)
    prediction_id = client.get("/history/predictions").json()["items"][0]["id"]

    detail = client.get(f"/history/predictions/{prediction_id}").json()

    assert detail["explanation"] is not None
    assert "top_features" in detail["explanation"]


def test_list_predictions_filters_by_severity(client, valid_record):
    client.post("/predict", json=valid_record)
    severity = client.get("/history/predictions").json()["items"][0]["severity"]

    matching = client.get(f"/history/predictions?severity={severity}").json()
    non_matching_severity = next(s for s in ["low", "medium", "high", "critical"] if s != severity)
    non_matching = client.get(f"/history/predictions?severity={non_matching_severity}").json()

    assert matching["total"] == 1
    assert non_matching["total"] == 0


def test_list_predictions_pagination_params(client, fixture_df):
    csv_bytes = fixture_df.to_csv(index=False).encode("utf-8")
    client.post("/predict/batch", files={"file": ("sample.csv", io.BytesIO(csv_bytes), "text/csv")})

    page = client.get("/history/predictions?limit=2&offset=0").json()

    assert page["total"] == len(fixture_df)
    assert len(page["items"]) == 2
    assert page["limit"] == 2
    assert page["offset"] == 0


def test_list_predictions_rejects_limit_over_max(client):
    response = client.get("/history/predictions?limit=1000")
    assert response.status_code == 422


def test_predict_raises_alert_and_it_appears_in_history(client, valid_record):
    predict_body = client.post("/predict", json=valid_record).json()
    assert predict_body["alert_id"] is not None

    alerts = client.get("/history/alerts").json()

    assert alerts["total"] == 1
    assert alerts["items"][0]["id"] == predict_body["alert_id"]
    assert alerts["items"][0]["acknowledged"] is False


def test_get_alert_by_id(client, valid_record):
    predict_body = client.post("/predict", json=valid_record).json()

    response = client.get(f"/history/alerts/{predict_body['alert_id']}")

    assert response.status_code == 200
    assert response.json()["id"] == predict_body["alert_id"]


def test_get_alert_404s_for_unknown_id(client):
    response = client.get("/history/alerts/does-not-exist")
    assert response.status_code == 404


def test_acknowledge_alert_flips_flag_and_persists(client, valid_record):
    predict_body = client.post("/predict", json=valid_record).json()
    alert_id = predict_body["alert_id"]

    ack_response = client.post(f"/history/alerts/{alert_id}/acknowledge")
    refetched = client.get(f"/history/alerts/{alert_id}")

    assert ack_response.status_code == 200
    assert ack_response.json()["acknowledged"] is True
    assert refetched.json()["acknowledged"] is True


def test_acknowledge_alert_404s_for_unknown_id(client):
    response = client.post("/history/alerts/does-not-exist/acknowledge")
    assert response.status_code == 404


def test_acknowledge_alert_records_audit_event(client, valid_record):
    predict_body = client.post("/predict", json=valid_record).json()
    alert_id = predict_body["alert_id"]

    client.post(f"/history/alerts/{alert_id}/acknowledge")
    body = client.get("/history/audit?event_type=alert_acknowledged").json()

    assert body["total"] == 1
    assert body["items"][0]["target_id"] == alert_id


def test_list_alerts_filters_by_acknowledged(client, valid_record):
    predict_body = client.post("/predict", json=valid_record).json()
    client.post(f"/history/alerts/{predict_body['alert_id']}/acknowledge")

    unacknowledged = client.get("/history/alerts?acknowledged=false").json()
    acknowledged = client.get("/history/alerts?acknowledged=true").json()

    assert unacknowledged["total"] == 0
    assert acknowledged["total"] == 1


def test_history_audit_503s_without_database(client_without_db):
    response = client_without_db.get("/history/audit")
    assert response.status_code == 503


def test_list_audit_events_empty_initially(client):
    response = client.get("/history/audit")

    assert response.status_code == 200
    body = response.json()
    assert body == {"items": [], "total": 0, "limit": 20, "offset": 0}


def test_list_audit_events_returns_recorded_events(client, tmp_path):
    from nids.api import store

    engine = store.create_db_engine(f"sqlite:///{tmp_path / 'history.db'}")
    store.record_audit_event(engine, event_type="device_paired", actor="127.0.0.1", target_id="device-1")

    body = client.get("/history/audit").json()

    assert body["total"] == 1
    assert body["items"][0]["event_type"] == "device_paired"
    assert body["items"][0]["target_id"] == "device-1"


def test_list_audit_events_filters_by_event_type_query_param(client, tmp_path):
    from nids.api import store

    engine = store.create_db_engine(f"sqlite:///{tmp_path / 'history.db'}")
    store.record_audit_event(engine, event_type="device_paired", actor="127.0.0.1")
    store.record_audit_event(engine, event_type="device_pair_failed", actor="127.0.0.1")

    body = client.get("/history/audit?event_type=device_pair_failed").json()

    assert body["total"] == 1
    assert body["items"][0]["event_type"] == "device_pair_failed"
