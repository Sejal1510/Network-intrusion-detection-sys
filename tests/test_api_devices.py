from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nids.api.app import create_app
from nids.api.config import ServingConfig
from nids.api.user_auth import create_session, register_user
from nids.data import loader
from nids.training.config import TrainingConfig
from nids.training.run import run_training

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd.txt"


@pytest.fixture
def fixture_df():
    return loader._read_nsl_kdd_file(FIXTURE)


@pytest.fixture
def app_with_db(fixture_df, tmp_path):
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        artifact_root=tmp_path / "runs",
        run_name="devices-fixture-run",
    )
    run_training(config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)

    serving_config = ServingConfig(
        run_id="devices-fixture-run",
        artifact_root=tmp_path / "runs",
        database_url=f"sqlite:///{tmp_path / 'history.db'}",
        secret_key="test-secret",
    )
    return create_app(serving_config)


def _auth_headers(app, username: str, role: str) -> dict:
    user = register_user(app.state.db_engine, username, "hunter2", role)
    session = create_session(app.state.db_engine, user.id, ttl_seconds=3600)
    return {"Authorization": f"Bearer {session.token}"}


def _pair_a_device(client: TestClient, device_name: str = "ayush-laptop") -> str:
    token = client.post("/agent/pair").json()["pairing_token"]
    return client.post(
        "/agent/pair/exchange", json={"pairing_token": token, "device_name": device_name}
    ).json()["device_id"]


def test_list_devices_requires_authentication(app_with_db):
    client = TestClient(app_with_db)

    response = client.get("/devices")

    assert response.status_code == 401


def test_list_devices_requires_admin_role(app_with_db):
    client = TestClient(app_with_db)
    headers = _auth_headers(app_with_db, "analyst1", "analyst")

    response = client.get("/devices", headers=headers)

    assert response.status_code == 403


def test_list_devices_returns_paired_devices(app_with_db):
    client = TestClient(app_with_db)
    _pair_a_device(client)
    headers = _auth_headers(app_with_db, "admin1", "admin")

    response = client.get("/devices", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["name"] == "ayush-laptop"


def test_revoke_device_requires_admin_role(app_with_db):
    client = TestClient(app_with_db)
    device_id = _pair_a_device(client)
    headers = _auth_headers(app_with_db, "analyst1", "analyst")

    response = client.post(f"/devices/{device_id}/revoke", headers=headers)

    assert response.status_code == 403


def test_revoke_device_marks_device_revoked(app_with_db):
    from nids.api.agent_auth import authenticate_device

    client = TestClient(app_with_db)
    token = client.post("/agent/pair").json()["pairing_token"]
    credential = client.post(
        "/agent/pair/exchange", json={"pairing_token": token, "device_name": "ayush-laptop"}
    ).json()
    headers = _auth_headers(app_with_db, "admin1", "admin")

    response = client.post(f"/devices/{credential['device_id']}/revoke", headers=headers)

    assert response.status_code == 200
    assert response.json()["revoked"] is True
    assert authenticate_device(app_with_db.state.db_engine, credential["token"]) is None


def test_revoke_device_404_for_unknown_id(app_with_db):
    client = TestClient(app_with_db)
    headers = _auth_headers(app_with_db, "admin1", "admin")

    response = client.post("/devices/does-not-exist/revoke", headers=headers)

    assert response.status_code == 404


def test_revoke_device_records_audit_event(app_with_db):
    client = TestClient(app_with_db)
    device_id = _pair_a_device(client)
    headers = _auth_headers(app_with_db, "admin1", "admin")

    client.post(f"/devices/{device_id}/revoke", headers=headers)
    audit = client.get("/history/audit?event_type=device_revoked", headers=headers).json()

    assert audit["total"] == 1
    assert audit["items"][0]["target_id"] == device_id
    assert audit["items"][0]["actor"] == "user:admin1"
