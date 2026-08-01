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
    row = fixture_df.iloc[0].to_dict()
    return {k: row[k] for k in FEATURE_COLUMNS}


@pytest.fixture
def app_with_db(fixture_df, tmp_path):
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        artifact_root=tmp_path / "runs",
        run_name="ingest-fixture-run",
    )
    run_training(config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)

    serving_config = ServingConfig(
        run_id="ingest-fixture-run",
        artifact_root=tmp_path / "runs",
        database_url=f"sqlite:///{tmp_path / 'history.db'}",
        secret_key="test-secret",
    )
    return create_app(serving_config)


@pytest.fixture
def app_without_db(fixture_df, tmp_path):
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        artifact_root=tmp_path / "runs",
        run_name="ingest-fixture-run",
    )
    run_training(config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)
    return create_app(ServingConfig(run_id="ingest-fixture-run", artifact_root=tmp_path / "runs"))


def test_pair_issues_a_pairing_token(app_with_db):
    client = TestClient(app_with_db)
    response = client.post("/agent/pair")

    assert response.status_code == 200
    body = response.json()
    assert body["pairing_token"]
    assert body["expires_in_seconds"] > 0


def test_pair_exchange_returns_device_credential(app_with_db):
    client = TestClient(app_with_db)
    token = client.post("/agent/pair").json()["pairing_token"]

    response = client.post(
        "/agent/pair/exchange", json={"pairing_token": token, "device_name": "ayush-laptop"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["device_id"]
    assert body["token"]


def test_pair_exchange_rejects_invalid_token(app_with_db):
    client = TestClient(app_with_db)
    response = client.post(
        "/agent/pair/exchange", json={"pairing_token": "garbage", "device_name": "x"}
    )
    assert response.status_code == 400


def test_pair_exchange_503s_without_database(app_without_db):
    client = TestClient(app_without_db)
    token = client.post("/agent/pair").json()["pairing_token"]

    response = client.post(
        "/agent/pair/exchange", json={"pairing_token": token, "device_name": "x"}
    )
    assert response.status_code == 503


def test_ingest_rejects_connection_without_credential(app_with_db):
    client = TestClient(app_with_db)
    # starlette raises WebSocketDisconnect on a refused handshake
    with pytest.raises(Exception), client.websocket_connect("/agent/ingest"):  # noqa: B017
        pass


class _RecordingBus:
    """A spy bus, standing in for InMemoryBus/RedisBus so the test can
    assert on what was published without racing against the real bus's
    asyncio.Queue across TestClient's background event loop."""

    def __init__(self):
        self.published: list[tuple[str, dict]] = []

    async def publish(self, channel, message):
        self.published.append((channel, message))

    async def subscribe(self, channel):
        return
        yield  # pragma: no cover -- unused by this test


def test_ingest_accepts_and_publishes_a_valid_flow_record(app_with_db, valid_record):
    client = TestClient(app_with_db)
    token = client.post("/agent/pair").json()["pairing_token"]
    device_token = client.post(
        "/agent/pair/exchange", json={"pairing_token": token, "device_name": "ayush-laptop"}
    ).json()["token"]

    recording_bus = _RecordingBus()
    app_with_db.state.bus = recording_bus

    with client.websocket_connect(
        "/agent/ingest", headers={"Authorization": f"Bearer {device_token}"}
    ) as ws:
        ws.send_json(valid_record)
        # messages on one WS connection are handled in order -- receiving
        # the error response for this second, invalid record proves the
        # first (valid) one was already published, without needing to
        # consume from the bus across a different event loop.
        ws.send_json({"not": "valid"})
        ws.receive_json()

    assert len(recording_bus.published) == 1
    channel, message = recording_bus.published[0]
    assert channel == "flows"
    assert message["record"]["service"] == valid_record["service"]
    assert message["device_id"]


def test_ingest_sends_error_for_invalid_flow_record_without_disconnecting(app_with_db, valid_record):
    client = TestClient(app_with_db)
    token = client.post("/agent/pair").json()["pairing_token"]
    device_token = client.post(
        "/agent/pair/exchange", json={"pairing_token": token, "device_name": "ayush-laptop"}
    ).json()["token"]

    incomplete = dict(valid_record)
    del incomplete["duration"]

    with client.websocket_connect(
        "/agent/ingest", headers={"Authorization": f"Bearer {device_token}"}
    ) as ws:
        ws.send_json(incomplete)
        response = ws.receive_json()
        assert response["type"] == "error"

        # connection must still be usable afterward
        ws.send_json(valid_record)
