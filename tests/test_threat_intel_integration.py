"""End-to-end: a live-agent flow record carrying a real (mocked-provider)
routable IPv4 indicator flows through ingest -> the live worker -> an
alert -> the enrichment dispatcher -> the cache -> and is retrievable via
GET /history/predictions/{id}/enrichment, with zero duplicated
prediction/risk/alert/enrichment logic anywhere in this path. Mirrors
tests/test_api_broadcast.py's existing end-to-end agent-flow tests
(Milestone 6), extended to also prove Milestone 16's asynchronous
enrichment dispatch. Uses `with TestClient(app) as client` (not the bare
constructor most of this suite uses) specifically so `_lifespan` actually
starts both the live worker *and* the enrichment dispatcher -- see
`nids.api.app._lifespan`'s docstring.
"""

from __future__ import annotations

import time
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
    record = {k: row[k] for k in FEATURE_COLUMNS}
    # What nids.flows.aggregator.FlowAggregator actually produces since
    # Milestone 16 -- a real capture agent's /agent/ingest payload, not a
    # hand-trimmed test fixture. 8.8.8.8 is a real, safe, routable public
    # IP (Google's public resolver) -- deliberately not a private/lab
    # address, since is_routable_ipv4 would otherwise correctly skip it
    # and this test would prove nothing about the enrichment path.
    record["src_ip"] = "10.0.0.5"  # the agent's own LAN -- correctly non-routable
    record["dst_ip"] = "8.8.8.8"
    return record


@pytest.fixture
def app(fixture_df, tmp_path):
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        artifact_root=tmp_path / "runs",
        run_name="threat-intel-integration-run",
    )
    run_training(config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)

    return create_app(
        ServingConfig(
            run_id="threat-intel-integration-run",
            artifact_root=tmp_path / "runs",
            database_url=f"sqlite:///{tmp_path / 'history.db'}",
            secret_key="test-secret",
            alert_threshold=0.0,  # every prediction raises an alert -- enrichment dispatch requires one
            abuseipdb_api_key="fake-key-for-this-test",
            greynoise_api_key="fake-key-for-this-test",
        )
    )


def _pair_device(client: TestClient, name: str = "integration-agent") -> str:
    pairing_token = client.post("/agent/pair").json()["pairing_token"]
    return client.post(
        "/agent/pair/exchange", json={"pairing_token": pairing_token, "device_name": name}
    ).json()["token"]


def _login_and_get_ws_ticket(client: TestClient, username: str = "analyst1") -> str:
    register_user(client.app.state.db_engine, username, "hunter2", "analyst")
    session_token = client.post(
        "/auth/login", json={"username": username, "password": "hunter2"}
    ).json()["token"]
    ticket = client.post(
        "/auth/ws-ticket", headers={"Authorization": f"Bearer {session_token}"}
    ).json()["ticket"]
    return session_token, ticket


def test_agent_flow_with_public_ip_is_enriched_end_to_end(app, valid_record, monkeypatch):
    captured_indicators = []

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._payload

    def fake_get(url, headers, timeout, params=None):
        # nids.api.threat_intel.abuseipdb and .greynoise both `import
        # requests` -- that's the same module object in sys.modules, so
        # a single fake dispatching on URL is required here, not two
        # separate monkeypatches (those would just overwrite each other).
        if "abuseipdb" in url:
            captured_indicators.append(params["ipAddress"])
            return FakeResponse(
                {"data": {"abuseConfidenceScore": 87, "totalReports": 40, "isWhitelisted": False}}
            )
        return FakeResponse({"classification": "malicious"})

    monkeypatch.setattr("nids.api.threat_intel.abuseipdb.requests.get", fake_get)

    with TestClient(app) as client:
        device_token = _pair_device(client)
        session_token, ticket = _login_and_get_ws_ticket(client)

        with (
            client.websocket_connect(f"/ws/live?ticket={ticket}") as live_ws,
            client.websocket_connect(
                "/agent/ingest", headers={"Authorization": f"Bearer {device_token}"}
            ) as ingest_ws,
        ):
            ingest_ws.send_json(valid_record)
            message = live_ws.receive_json()

        assert message["type"] == "prediction"
        assert message["data"]["alert_id"] is not None

        # Persistence (prediction/alert) is synchronous-by-the-time-the-
        # live message arrives; enrichment is fire-and-forget on top of
        # that, so it may still be in flight -- poll briefly rather than
        # assuming it's already landed.
        prediction_id = _find_prediction_id(client, session_token)
        items = _poll_for_enrichment(client, session_token, prediction_id)

    assert captured_indicators == ["8.8.8.8"]  # never the private 10.0.0.5 side
    by_provider = {item["provider"]: item for item in items}
    assert by_provider["abuseipdb"]["verdict"] == "malicious"
    assert by_provider["abuseipdb"]["indicator"] == "8.8.8.8"
    assert by_provider["abuseipdb"]["indicator_role"] == "dst"
    assert by_provider["greynoise"]["verdict"] == "malicious"


def _find_prediction_id(client: TestClient, session_token: str) -> str:
    headers = {"Authorization": f"Bearer {session_token}"}
    page = client.get("/history/predictions?limit=1", headers=headers).json()
    assert page["items"], "expected the just-processed prediction to already be persisted"
    return page["items"][0]["id"]


def _poll_for_enrichment(client: TestClient, session_token: str, prediction_id: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {session_token}"}
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        items = client.get(
            f"/history/predictions/{prediction_id}/enrichment", headers=headers
        ).json()["items"]
        if len(items) == 2:  # both providers have landed
            return items
        time.sleep(0.05)
    raise AssertionError("enrichment did not complete within the test's deadline")
