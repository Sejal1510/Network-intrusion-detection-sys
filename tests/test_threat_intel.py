import asyncio
import os

import pytest

from nids.api.config import ServingConfig
from nids.api.metrics import create_metrics
from nids.api.store import create_db_engine, get_cached_enrichment
from nids.api.threat_intel import (
    EnrichmentResult,
    build_providers,
    extract_indicators,
    is_routable_ipv4,
)
from nids.api.threat_intel.abuseipdb import AbuseIPDBProvider
from nids.api.threat_intel.dispatcher import dispatch_enrichment, run_enrichment_dispatcher
from nids.api.threat_intel.greynoise import GreyNoiseProvider
from nids.api.threat_intel.publish import schedule_enrichment_publish


def _result(indicator="1.2.3.4", provider="abuseipdb", verdict="malicious", confidence=90.0) -> EnrichmentResult:
    return EnrichmentResult(
        indicator=indicator,
        provider=provider,
        verdict=verdict,
        confidence=confidence,
        raw_response={"ok": True},
    )


# --- EnrichmentResult --------------------------------------------------------


def test_enrichment_result_rejects_invalid_verdict():
    with pytest.raises(ValueError):
        EnrichmentResult(indicator="1.2.3.4", provider="x", verdict="evil", confidence=0, raw_response={})


# --- is_routable_ipv4 / extract_indicators -----------------------------------


@pytest.mark.parametrize(
    "value",
    ["10.0.0.1", "172.16.5.5", "192.168.1.1", "127.0.0.1", "169.254.1.1", "224.0.0.1", "0.0.0.0"],
)
def test_is_routable_ipv4_rejects_non_routable(value):
    assert is_routable_ipv4(value) is False


@pytest.mark.parametrize("value", ["8.8.8.8", "1.1.1.1", "9.9.9.9"])
def test_is_routable_ipv4_accepts_public_addresses(value):
    assert is_routable_ipv4(value) is True


def test_is_routable_ipv4_rejects_documentation_range():
    """RFC 5737 TEST-NET ranges (203.0.113.0/24 among them) are
    IANA-reserved for documentation -- Python's `ipaddress` correctly
    classifies them under `is_private`, and no real provider would have
    meaningful data for one anyway."""
    assert is_routable_ipv4("203.0.113.5") is False


def test_is_routable_ipv4_rejects_ipv6_none_and_garbage():
    assert is_routable_ipv4("2001:db8::1") is False
    assert is_routable_ipv4(None) is False
    assert is_routable_ipv4("not-an-ip") is False
    assert is_routable_ipv4("") is False


def test_extract_indicators_dedupes_and_filters_non_routable():
    record = {"src_ip": "10.0.0.1", "dst_ip": "8.8.8.8"}
    assert extract_indicators(record) == ["8.8.8.8"]


def test_extract_indicators_dedupes_identical_src_and_dst():
    record = {"src_ip": "8.8.8.8", "dst_ip": "8.8.8.8"}
    assert extract_indicators(record) == ["8.8.8.8"]


def test_extract_indicators_empty_for_api_sourced_record_with_no_ip_keys():
    """The whole reason this function exists: /predict and /predict/batch
    records (NSL-KDD-shaped) never have src_ip/dst_ip at all."""
    record = {"duration": 0, "protocol_type": "tcp"}
    assert extract_indicators(record) == []


# --- AbuseIPDBProvider --------------------------------------------------------


def test_abuseipdb_maps_high_score_to_malicious(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"abuseConfidenceScore": 90, "totalReports": 12, "isWhitelisted": False}}

    monkeypatch.setattr("nids.api.threat_intel.abuseipdb.requests.get", lambda *a, **kw: FakeResponse())

    result = AbuseIPDBProvider("key").lookup("1.2.3.4")

    assert result.verdict == "malicious"
    assert result.confidence == 90.0
    assert result.provider == "abuseipdb"
    assert result.indicator == "1.2.3.4"


def test_abuseipdb_maps_mid_score_to_suspicious(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"abuseConfidenceScore": 40, "totalReports": 3, "isWhitelisted": False}}

    monkeypatch.setattr("nids.api.threat_intel.abuseipdb.requests.get", lambda *a, **kw: FakeResponse())
    assert AbuseIPDBProvider("key").lookup("1.2.3.4").verdict == "suspicious"


def test_abuseipdb_maps_zero_reports_to_unknown(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"abuseConfidenceScore": 0, "totalReports": 0, "isWhitelisted": False}}

    monkeypatch.setattr("nids.api.threat_intel.abuseipdb.requests.get", lambda *a, **kw: FakeResponse())
    assert AbuseIPDBProvider("key").lookup("1.2.3.4").verdict == "unknown"


def test_abuseipdb_whitelisted_is_always_benign_regardless_of_score(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"abuseConfidenceScore": 80, "totalReports": 5, "isWhitelisted": True}}

    monkeypatch.setattr("nids.api.threat_intel.abuseipdb.requests.get", lambda *a, **kw: FakeResponse())
    assert AbuseIPDBProvider("key").lookup("1.2.3.4").verdict == "benign"


def test_abuseipdb_sends_the_expected_request(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": {"abuseConfidenceScore": 0, "totalReports": 0}}

    def fake_get(url, headers, params, timeout):
        captured.update(url=url, headers=headers, params=params, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr("nids.api.threat_intel.abuseipdb.requests.get", fake_get)
    AbuseIPDBProvider("my-key").lookup("1.2.3.4")

    assert captured["headers"]["Key"] == "my-key"
    assert captured["params"]["ipAddress"] == "1.2.3.4"
    assert captured["timeout"] == 5.0


def test_abuseipdb_raises_on_http_error(monkeypatch):
    class FailingResponse:
        def raise_for_status(self):
            raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(
        "nids.api.threat_intel.abuseipdb.requests.get", lambda *a, **kw: FailingResponse()
    )
    with pytest.raises(RuntimeError):
        AbuseIPDBProvider("key").lookup("1.2.3.4")


def test_abuseipdb_raises_on_timeout(monkeypatch):
    import requests

    def raise_timeout(*a, **kw):
        raise requests.exceptions.Timeout("timed out")

    monkeypatch.setattr("nids.api.threat_intel.abuseipdb.requests.get", raise_timeout)
    with pytest.raises(requests.exceptions.Timeout):
        AbuseIPDBProvider("key").lookup("1.2.3.4")


# --- GreyNoiseProvider ---------------------------------------------------------


def test_greynoise_passes_through_native_classification(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"classification": "malicious", "noise": True, "riot": False}

    monkeypatch.setattr("nids.api.threat_intel.greynoise.requests.get", lambda *a, **kw: FakeResponse())

    result = GreyNoiseProvider("key").lookup("1.2.3.4")

    assert result.verdict == "malicious"
    assert result.confidence == 90.0
    assert result.provider == "greynoise"


def test_greynoise_maps_unrecognized_classification_to_unknown(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"classification": "something-new-greynoise-added"}

    monkeypatch.setattr("nids.api.threat_intel.greynoise.requests.get", lambda *a, **kw: FakeResponse())
    result = GreyNoiseProvider("key").lookup("1.2.3.4")
    assert result.verdict == "unknown"
    assert result.confidence == 0.0


def test_greynoise_sends_the_expected_request(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"classification": "benign"}

    def fake_get(url, headers, timeout):
        captured.update(url=url, headers=headers, timeout=timeout)
        return FakeResponse()

    monkeypatch.setattr("nids.api.threat_intel.greynoise.requests.get", fake_get)
    GreyNoiseProvider("my-key").lookup("1.2.3.4")

    assert captured["url"].endswith("/1.2.3.4")
    assert captured["headers"]["key"] == "my-key"


def test_greynoise_raises_on_http_error(monkeypatch):
    class FailingResponse:
        def raise_for_status(self):
            raise RuntimeError("503 Service Unavailable")

    monkeypatch.setattr(
        "nids.api.threat_intel.greynoise.requests.get", lambda *a, **kw: FailingResponse()
    )
    with pytest.raises(RuntimeError):
        GreyNoiseProvider("key").lookup("1.2.3.4")


# --- build_providers -----------------------------------------------------------


def test_build_providers_empty_when_nothing_configured():
    config = ServingConfig(run_id="test-run")
    assert build_providers(config) == []


def test_build_providers_includes_abuseipdb_only_when_key_set():
    config = ServingConfig(run_id="test-run", abuseipdb_api_key="key")
    providers = build_providers(config)
    assert len(providers) == 1
    assert isinstance(providers[0], AbuseIPDBProvider)


def test_build_providers_includes_both_when_both_configured():
    config = ServingConfig(
        run_id="test-run", abuseipdb_api_key="a-key", greynoise_api_key="g-key"
    )
    providers = build_providers(config)
    assert len(providers) == 2
    assert {type(p) for p in providers} == {AbuseIPDBProvider, GreyNoiseProvider}


# --- dispatch_enrichment -------------------------------------------------------


class _FakeProvider:
    def __init__(self, name, *, fail=False, verdict="malicious"):
        self.name = name
        self.fail = fail
        self.verdict = verdict
        self.calls: list[str] = []

    def lookup(self, indicator: str) -> EnrichmentResult:
        self.calls.append(indicator)
        if self.fail:
            raise RuntimeError("provider unavailable")
        return _result(indicator=indicator, provider=self.name, verdict=self.verdict)


@pytest.fixture
def engine(tmp_path):
    return create_db_engine(f"sqlite:///{tmp_path / 'test.db'}")


async def test_dispatch_enrichment_calls_every_provider_and_caches_result(engine):
    a, b = _FakeProvider("abuseipdb"), _FakeProvider("greynoise")
    await dispatch_enrichment(["1.2.3.4"], [a, b], 86_400, engine)

    assert a.calls == ["1.2.3.4"]
    assert b.calls == ["1.2.3.4"]
    assert get_cached_enrichment(engine, "1.2.3.4", "abuseipdb") is not None
    assert get_cached_enrichment(engine, "1.2.3.4", "greynoise") is not None


async def test_dispatch_enrichment_one_provider_failing_does_not_stop_the_other(engine):
    failing, ok = _FakeProvider("abuseipdb", fail=True), _FakeProvider("greynoise")
    await dispatch_enrichment(["1.2.3.4"], [failing, ok], 86_400, engine)

    assert get_cached_enrichment(engine, "1.2.3.4", "abuseipdb") is None
    assert get_cached_enrichment(engine, "1.2.3.4", "greynoise") is not None


async def test_dispatch_enrichment_skips_provider_call_when_cache_is_fresh(engine):
    provider = _FakeProvider("abuseipdb")
    await dispatch_enrichment(["1.2.3.4"], [provider], 86_400, engine)
    assert provider.calls == ["1.2.3.4"]

    await dispatch_enrichment(["1.2.3.4"], [provider], 86_400, engine)
    assert provider.calls == ["1.2.3.4"]  # still just the one call -- second was a cache hit


async def test_dispatch_enrichment_re_queries_when_cache_is_expired(engine):
    provider = _FakeProvider("abuseipdb")
    await dispatch_enrichment(["1.2.3.4"], [provider], -1, engine)  # expires immediately
    assert provider.calls == ["1.2.3.4"]

    await dispatch_enrichment(["1.2.3.4"], [provider], 86_400, engine)
    assert provider.calls == ["1.2.3.4", "1.2.3.4"]


async def test_dispatch_enrichment_records_metrics_for_success_and_failure(engine):
    metrics = create_metrics()
    failing, ok = _FakeProvider("abuseipdb", fail=True), _FakeProvider("greynoise")

    await dispatch_enrichment(["1.2.3.4"], [failing, ok], 86_400, engine, metrics)

    assert metrics.ioc_enrichment_lookups_total.labels(provider="abuseipdb", status="failure")._value.get() == 1
    assert metrics.ioc_enrichment_lookups_total.labels(provider="greynoise", status="success")._value.get() == 1


async def test_run_enrichment_dispatcher_consumes_published_indicators(engine):
    from nids.api.bus import InMemoryBus
    from nids.api.threat_intel.publish import _publish_indicators

    bus = InMemoryBus()
    provider = _FakeProvider("abuseipdb")

    task = asyncio.create_task(run_enrichment_dispatcher(bus, [provider], 86_400, engine))
    try:
        await asyncio.sleep(0.05)  # InMemoryBus is real Pub/Sub -- subscribe before publish
        await _publish_indicators(bus, ["1.2.3.4"])
        await asyncio.sleep(0.05)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert provider.calls == ["1.2.3.4"]


async def test_run_enrichment_dispatcher_drops_malformed_message_without_dying(engine):
    from nids.api.bus import InMemoryBus

    bus = InMemoryBus()
    provider = _FakeProvider("abuseipdb")

    task = asyncio.create_task(run_enrichment_dispatcher(bus, [provider], 86_400, engine))
    try:
        await asyncio.sleep(0.05)
        await bus.publish("enrichment", {"indicators": "not-a-list"})  # malformed
        await asyncio.sleep(0.05)
        await bus.publish("enrichment", {"indicators": ["5.6.7.8"]})  # well-formed, after the bad one
        await asyncio.sleep(0.05)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    assert provider.calls == ["5.6.7.8"]  # the dispatcher loop survived the malformed message


# --- schedule_enrichment_publish -----------------------------------------------


async def test_schedule_enrichment_publish_delivers_to_subscriber():
    from nids.api.bus import InMemoryBus

    bus = InMemoryBus()
    loop = asyncio.get_running_loop()

    async def collect_one():
        async for message in bus.subscribe("enrichment"):
            return message

    subscriber = asyncio.create_task(collect_one())
    await asyncio.sleep(0.05)

    schedule_enrichment_publish(bus, loop, ["9.9.9.9"])

    message = await asyncio.wait_for(subscriber, timeout=1.0)
    assert message["indicators"] == ["9.9.9.9"]


# --- Real-provider end-to-end (only runs with a real credential supplied) -----


@pytest.mark.skipif(
    not os.environ.get("ABUSEIPDB_API_KEY"),
    reason="set ABUSEIPDB_API_KEY to run a real AbuseIPDB lookup end-to-end",
)
def test_abuseipdb_real_lookup_against_a_known_public_resolver():
    """Not run in CI (no secrets there) -- a real, credentialed sanity
    check that this project's request/response handling matches
    AbuseIPDB's actual API, not just our own mocked assumptions about it.
    1.1.1.1 (Cloudflare's public resolver) is a stable, safe, real-world
    indicator to query -- almost certainly reported at some nonzero rate
    (it's one of the most-queried IPs on the internet) but not something
    that could ever be considered a risky or sensitive lookup."""
    provider = AbuseIPDBProvider(os.environ["ABUSEIPDB_API_KEY"])
    result = provider.lookup("1.1.1.1")

    assert result.indicator == "1.1.1.1"
    assert result.verdict in {"malicious", "suspicious", "benign", "unknown"}
    assert 0.0 <= result.confidence <= 100.0
    assert "data" in result.raw_response


@pytest.mark.skipif(
    not os.environ.get("GREYNOISE_API_KEY"),
    reason="set GREYNOISE_API_KEY to run a real GreyNoise lookup end-to-end",
)
def test_greynoise_real_lookup_against_a_known_public_resolver():
    provider = GreyNoiseProvider(os.environ["GREYNOISE_API_KEY"])
    result = provider.lookup("1.1.1.1")

    assert result.indicator == "1.1.1.1"
    assert result.verdict in {"malicious", "suspicious", "benign", "unknown"}
