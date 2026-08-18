from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nids.api.app import create_app
from nids.api.config import ServingConfig
from nids.api.user_auth import register_user
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
    row = fixture_df.iloc[0].to_dict()
    return {k: row[k] for k in FEATURE_COLUMNS}


@pytest.fixture
def app_with_db(fixture_df, tmp_path):
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        artifact_root=tmp_path / "runs",
        run_name="broadcast-fixture-run",
    )
    run_training(config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)

    serving_config = ServingConfig(
        run_id="broadcast-fixture-run",
        artifact_root=tmp_path / "runs",
        database_url=f"sqlite:///{tmp_path / 'history.db'}",
        secret_key="test-secret",
        alert_threshold=0.0,
    )
    return create_app(serving_config)


@pytest.fixture
def app_without_db(fixture_df, tmp_path):
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        artifact_root=tmp_path / "runs",
        run_name="broadcast-fixture-run",
    )
    run_training(config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)
    return create_app(ServingConfig(run_id="broadcast-fixture-run", artifact_root=tmp_path / "runs"))


def _pair_device(client: TestClient, name: str = "ayush-laptop") -> str:
    """Still the right way to authenticate the *agent* side
    (`/agent/ingest`) -- only `/ws/live`'s auth moved to session tickets
    in Milestone 15, since that side is the actual capture agent, not a
    browser tab standing in as one."""
    pairing_token = client.post("/agent/pair").json()["pairing_token"]
    return client.post(
        "/agent/pair/exchange", json={"pairing_token": pairing_token, "device_name": name}
    ).json()["token"]


def _login_and_get_ws_ticket(client: TestClient, username: str = "analyst1") -> str:
    login = client.post("/auth/login", json={"username": username, "password": "hunter2"})
    session_token = login.json()["token"]
    ticket = client.post(
        "/auth/ws-ticket", headers={"Authorization": f"Bearer {session_token}"}
    )
    return ticket.json()["ticket"]


@pytest.fixture
def dashboard_user(app_with_db):
    return register_user(app_with_db.state.db_engine, "analyst1", "hunter2", "analyst")


def test_live_503s_without_database(app_without_db):
    client = TestClient(app_without_db)
    with pytest.raises(Exception), client.websocket_connect("/ws/live?ticket=anything"):  # noqa: B017
        pass


def test_live_rejects_invalid_ticket(app_with_db):
    client = TestClient(app_with_db)
    with pytest.raises(Exception), client.websocket_connect("/ws/live?ticket=not-a-real-ticket"):  # noqa: B017
        pass


def test_live_rejects_a_device_credential(app_with_db, dashboard_user):
    """/ws/live no longer accepts the agent's device-credential token at
    all -- confirms the two auth systems stayed genuinely separate after
    the Milestone 15 rework, not just "usually" separate."""
    client = TestClient(app_with_db)
    device_token = _pair_device(client)
    with pytest.raises(Exception), client.websocket_connect(f"/ws/live?ticket={device_token}"):  # noqa: B017
        pass


def test_live_accepts_valid_ws_ticket(app_with_db, dashboard_user):
    client = TestClient(app_with_db)
    ticket = _login_and_get_ws_ticket(client)

    with client.websocket_connect(f"/ws/live?ticket={ticket}"):
        pass  # connecting and cleanly closing must not raise


def test_ws_ticket_requires_login(app_with_db):
    client = TestClient(app_with_db)
    response = client.post("/auth/ws-ticket")
    assert response.status_code == 401


def test_end_to_end_agent_flow_reaches_live_dashboard(app_with_db, valid_record, dashboard_user):
    """The whole point of Milestone 6: a flow record submitted by an
    agent over /agent/ingest flows through the live worker
    (nids.api.pipeline.process_record -- the exact same orchestration
    /predict uses) and arrives at a dashboard's /ws/live connection,
    with zero duplicated prediction/risk/alert logic anywhere in this
    path. The agent side authenticates with its device credential; the
    dashboard side authenticates with a session-backed ws-ticket -- two
    distinct identities meeting on the same bus channel, per Milestone 15."""
    with TestClient(app_with_db) as client:
        device_token = _pair_device(client)
        ticket = _login_and_get_ws_ticket(client)

        with (
            client.websocket_connect(f"/ws/live?ticket={ticket}") as live_ws,
            client.websocket_connect(
                "/agent/ingest", headers={"Authorization": f"Bearer {device_token}"}
            ) as ingest_ws,
        ):
            ingest_ws.send_json(valid_record)
            message = live_ws.receive_json()

    assert message["type"] == "prediction"
    data = message["data"]
    assert data["prediction"] is not None
    assert data["risk_score"] is not None
    assert data["severity"] in {"critical", "high", "medium", "low"}


def test_end_to_end_flow_is_retrievable_via_history_afterward(app_with_db, valid_record, dashboard_user):
    from nids.api import store

    with TestClient(app_with_db) as client:
        device_token = _pair_device(client)
        ticket = _login_and_get_ws_ticket(client)

        with (
            client.websocket_connect(f"/ws/live?ticket={ticket}") as live_ws,
            client.websocket_connect(
                "/agent/ingest", headers={"Authorization": f"Bearer {device_token}"}
            ) as ingest_ws,
        ):
            ingest_ws.send_json(valid_record)
            live_ws.receive_json()  # wait for the worker to have finished processing

        page = store.list_predictions(app_with_db.state.db_engine)

    assert page.total == 1
    assert page.items[0].source == "agent"
    assert page.items[0].device_id is not None
