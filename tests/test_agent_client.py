import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import websockets
import websockets.exceptions

from nids.agent import client as client_module
from nids.agent.client import AgentClient, exchange_pairing_token, request_pairing_token


class _FakeSource:
    def __init__(self, records: list[dict]):
        self._records = records

    async def records(self):
        for record in self._records:
            yield record
        await asyncio.Event().wait()  # matches FlowSource's infinite-stream contract


def _mock_response(json_body: dict) -> MagicMock:
    response = MagicMock()
    response.json.return_value = json_body
    response.raise_for_status.return_value = None
    return response


def test_request_pairing_token_posts_and_parses_response(monkeypatch):
    captured = {}

    def fake_post(url, timeout=None, **kwargs):
        captured["url"] = url
        return _mock_response({"pairing_token": "abc123", "expires_in_seconds": 600})

    monkeypatch.setattr(client_module.requests, "post", fake_post)

    token = request_pairing_token("http://localhost:8000")

    assert token == "abc123"
    assert captured["url"] == "http://localhost:8000/agent/pair"


def test_exchange_pairing_token_posts_payload_and_parses_response(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        return _mock_response({"device_id": "dev-1", "token": "device-token-xyz"})

    monkeypatch.setattr(client_module.requests, "post", fake_post)

    token = exchange_pairing_token("http://localhost:8000", "pairing-code", "ayush-laptop")

    assert token == "device-token-xyz"
    assert captured["url"] == "http://localhost:8000/agent/pair/exchange"
    assert captured["json"] == {"pairing_token": "pairing-code", "device_name": "ayush-laptop"}


async def test_produce_buffers_records_from_source():
    source = _FakeSource([{"n": 1}, {"n": 2}, {"n": 3}])
    agent = AgentClient("ws://x", "token", source, buffer_size=10)

    task = asyncio.create_task(agent._produce())
    await asyncio.sleep(0.05)
    task.cancel()

    assert list(agent._buffer) == [{"n": 1}, {"n": 2}, {"n": 3}]


async def test_produce_drops_oldest_when_buffer_is_full():
    source = _FakeSource([{"n": 1}, {"n": 2}, {"n": 3}])
    agent = AgentClient("ws://x", "token", source, buffer_size=2)

    task = asyncio.create_task(agent._produce())
    await asyncio.sleep(0.05)
    task.cancel()

    assert list(agent._buffer) == [{"n": 2}, {"n": 3}]


async def test_drain_sends_buffered_records():
    sent = []

    class _FakeWs:
        async def send(self, payload):
            sent.append(payload)

    agent = AgentClient("ws://x", "token", _FakeSource([]), buffer_size=10)
    agent._buffer.append({"n": 1})
    agent._buffer_not_empty.set()

    task = asyncio.create_task(agent._drain(_FakeWs()))
    await asyncio.sleep(0.05)
    task.cancel()

    assert len(sent) == 1
    assert '"n": 1' in sent[0]
    assert len(agent._buffer) == 0


async def test_drain_puts_record_back_on_send_failure():
    class _FailingWs:
        async def send(self, payload):
            raise OSError("connection reset")

    agent = AgentClient("ws://x", "token", _FakeSource([]), buffer_size=10)
    agent._buffer.append({"n": 1})
    agent._buffer_not_empty.set()

    with pytest.raises(OSError, match="connection reset"):
        await agent._drain(_FailingWs())

    assert list(agent._buffer) == [{"n": 1}]  # put back, not lost


async def test_send_loop_reconnects_after_a_failed_attempt(monkeypatch):
    # `client_module.asyncio` is the real `asyncio` module object, so
    # monkeypatching `.sleep` on it would patch `asyncio.sleep` globally --
    # including this test's own synchronization -- not just the call inside
    # `_send_loop`. Swap in a namespace object instead, so only client.py's
    # `asyncio.sleep` lookup is affected.
    sleep_calls = []
    second_attempt_made = asyncio.Event()

    async def fake_sleep(delay):
        sleep_calls.append(delay)
        # A real (zero-length) suspension point: `_send_loop` has no other
        # `await` that actually yields when every collaborator is faked, so
        # without this the retry loop spins the event loop forever and the
        # test below never gets a turn to run.
        await asyncio.sleep(0)

    class _FakeWsConnection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def send(self, payload):
            raise websockets.exceptions.ConnectionClosed(None, None)

    attempts = {"n": 0}

    def fake_connect(url, **kwargs):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise OSError("refused")
        second_attempt_made.set()
        return _FakeWsConnection()

    monkeypatch.setattr(client_module.websockets, "connect", fake_connect)

    agent = AgentClient("ws://x", "token", _FakeSource([]), buffer_size=10)
    agent._buffer.append({"n": 1})
    agent._buffer_not_empty.set()

    monkeypatch.setattr(client_module, "asyncio", SimpleNamespace(sleep=fake_sleep))

    task = asyncio.create_task(agent._send_loop())
    await asyncio.wait_for(second_attempt_made.wait(), timeout=1)
    task.cancel()

    assert attempts["n"] >= 2  # first attempt failed, retried
    assert len(sleep_calls) >= 1  # backoff was applied
