import argparse
import json
from types import SimpleNamespace

import pytest

from nids.agent import cli as cli_module
from nids.agent.sources import LiveSource, ReplaySource


def test_ws_url_from_base_converts_http_to_ws():
    assert cli_module.ws_url_from_base("http://localhost:8000") == "ws://localhost:8000/agent/ingest"


def test_ws_url_from_base_converts_https_to_wss():
    assert (
        cli_module.ws_url_from_base("https://example.com/")
        == "wss://example.com/agent/ingest"
    )


def test_save_and_load_device_credential_roundtrip(tmp_path):
    path = tmp_path / "nested" / "credential.json"

    cli_module.save_device_credential(path, "device-token-xyz")

    assert cli_module.load_device_credential(path) == "device-token-xyz"
    assert json.loads(path.read_text()) == {"token": "device-token-xyz"}


def test_load_device_credential_missing_file_raises_system_exit(tmp_path):
    path = tmp_path / "missing.json"

    with pytest.raises(SystemExit, match="pair"):
        cli_module.load_device_credential(path)


def test_build_source_returns_replay_source_when_pcap_given():
    args = argparse.Namespace(pcap="capture.pcap", speed=2.0, interface=None, bpf_filter=None)

    source = cli_module.build_source(args)

    assert isinstance(source, ReplaySource)
    assert source._pcap_path == "capture.pcap"
    assert source._speed == 2.0


def test_build_source_returns_live_source_by_default():
    args = argparse.Namespace(pcap=None, speed=1.0, interface="eth0", bpf_filter="tcp")

    source = cli_module.build_source(args)

    assert isinstance(source, LiveSource)


def test_pair_command_exchanges_token_and_saves_credential(tmp_path, monkeypatch):
    captured = {}

    def fake_exchange(base_url, pairing_token, device_name):
        captured["args"] = (base_url, pairing_token, device_name)
        return "device-token-xyz"

    monkeypatch.setattr(cli_module, "exchange_pairing_token", fake_exchange)

    credential_file = tmp_path / "credential.json"
    args = argparse.Namespace(
        base_url="http://localhost:8000",
        pairing_code="abc123",
        device_name="ayush-laptop",
        credential_file=credential_file,
    )

    exit_code = cli_module._pair(args)

    assert exit_code == 0
    assert captured["args"] == ("http://localhost:8000", "abc123", "ayush-laptop")
    assert cli_module.load_device_credential(credential_file) == "device-token-xyz"


def test_run_command_builds_client_from_saved_credential_and_runs_it(tmp_path, monkeypatch):
    credential_file = tmp_path / "credential.json"
    cli_module.save_device_credential(credential_file, "device-token-xyz")

    constructed = {}

    class _FakeAgentClient:
        def __init__(self, ws_url, device_token, source):
            constructed["ws_url"] = ws_url
            constructed["device_token"] = device_token
            constructed["source"] = source

        async def run(self):
            constructed["ran"] = True

    monkeypatch.setattr(cli_module, "AgentClient", _FakeAgentClient)

    run_calls = []

    def fake_run(coro):
        run_calls.append(coro)
        coro.close()  # avoid "coroutine was never awaited" -- we're not exercising it here

    monkeypatch.setattr(cli_module, "asyncio", SimpleNamespace(run=fake_run))

    args = argparse.Namespace(
        base_url="http://localhost:8000",
        credential_file=credential_file,
        pcap=None,
        speed=1.0,
        interface=None,
        bpf_filter=None,
    )

    exit_code = cli_module._run(args)

    assert exit_code == 0
    assert constructed["ws_url"] == "ws://localhost:8000/agent/ingest"
    assert constructed["device_token"] == "device-token-xyz"
    assert isinstance(constructed["source"], LiveSource)
    assert len(run_calls) == 1
