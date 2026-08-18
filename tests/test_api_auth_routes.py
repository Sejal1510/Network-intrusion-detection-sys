from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nids.api.app import create_app
from nids.api.config import ServingConfig
from nids.api.user_auth import register_user
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
        run_name="auth-fixture-run",
    )
    run_training(config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)

    serving_config = ServingConfig(
        run_id="auth-fixture-run",
        artifact_root=tmp_path / "runs",
        database_url=f"sqlite:///{tmp_path / 'history.db'}",
    )
    return create_app(serving_config)


@pytest.fixture
def analyst_user(app_with_db):
    return register_user(app_with_db.state.db_engine, "analyst1", "hunter2", "analyst")


def test_login_succeeds_with_correct_credentials(app_with_db, analyst_user):
    client = TestClient(app_with_db)

    response = client.post("/auth/login", json={"username": "analyst1", "password": "hunter2"})

    assert response.status_code == 200
    body = response.json()
    assert body["token"]
    assert body["username"] == "analyst1"
    assert body["role"] == "analyst"


def test_login_fails_with_wrong_password(app_with_db, analyst_user):
    client = TestClient(app_with_db)

    response = client.post("/auth/login", json={"username": "analyst1", "password": "wrong"})

    assert response.status_code == 401


def test_login_fails_for_unknown_username(app_with_db):
    client = TestClient(app_with_db)

    response = client.post("/auth/login", json={"username": "nobody", "password": "x"})

    assert response.status_code == 401


def test_login_rate_limited_after_threshold(app_with_db, analyst_user):
    app_with_db.state.serving_config = ServingConfig(
        run_id=app_with_db.state.serving_config.run_id,
        artifact_root=app_with_db.state.serving_config.artifact_root,
        database_url=app_with_db.state.serving_config.database_url,
        auth_rate_limit_per_minute=1,
    )
    client = TestClient(app_with_db)

    first = client.post("/auth/login", json={"username": "analyst1", "password": "hunter2"})
    second = client.post("/auth/login", json={"username": "analyst1", "password": "hunter2"})

    assert first.status_code == 200
    assert second.status_code == 429


def test_me_requires_authentication(app_with_db):
    client = TestClient(app_with_db)

    response = client.get("/auth/me")

    assert response.status_code == 401


def test_me_returns_current_user_with_valid_token(app_with_db, analyst_user):
    client = TestClient(app_with_db)
    token = client.post(
        "/auth/login", json={"username": "analyst1", "password": "hunter2"}
    ).json()["token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {"username": "analyst1", "role": "analyst"}


def test_logout_revokes_the_session(app_with_db, analyst_user):
    client = TestClient(app_with_db)
    token = client.post(
        "/auth/login", json={"username": "analyst1", "password": "hunter2"}
    ).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    logout_response = client.post("/auth/logout", headers=headers)
    me_response = client.get("/auth/me", headers=headers)

    assert logout_response.status_code == 204
    assert me_response.status_code == 401


def test_logout_requires_authentication(app_with_db):
    client = TestClient(app_with_db)

    response = client.post("/auth/logout")

    assert response.status_code == 401


def test_ws_ticket_succeeds_for_a_logged_in_user(app_with_db, analyst_user):
    client = TestClient(app_with_db)
    token = client.post(
        "/auth/login", json={"username": "analyst1", "password": "hunter2"}
    ).json()["token"]

    response = client.post("/auth/ws-ticket", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["ticket"]
    assert body["expires_in_seconds"] > 0


def test_ws_ticket_requires_authentication(app_with_db):
    client = TestClient(app_with_db)

    response = client.post("/auth/ws-ticket")

    assert response.status_code == 401


def test_ws_ticket_is_unusable_after_logout(app_with_db, analyst_user):
    """A revoked session can't mint a fresh ticket -- the whole point of
    tying /ws/live's auth to real sessions instead of a non-expiring
    device credential (see nids.api.broadcast's module docstring)."""
    client = TestClient(app_with_db)
    token = client.post(
        "/auth/login", json={"username": "analyst1", "password": "hunter2"}
    ).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/auth/logout", headers=headers)

    response = client.post("/auth/ws-ticket", headers=headers)

    assert response.status_code == 401
