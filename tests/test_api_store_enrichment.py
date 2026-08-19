from datetime import datetime, timezone

import pytest

from nids.api.store import (
    create_db_engine,
    get_cached_enrichment,
    list_enrichments_for_indicators,
    upsert_enrichment,
)
from nids.api.threat_intel import EnrichmentResult


@pytest.fixture
def engine(tmp_path):
    return create_db_engine(f"sqlite:///{tmp_path / 'test.db'}")


def _result(indicator="1.2.3.4", provider="abuseipdb", verdict="malicious", confidence=90.0) -> EnrichmentResult:
    return EnrichmentResult(
        indicator=indicator,
        provider=provider,
        verdict=verdict,
        confidence=confidence,
        raw_response={"some": "payload"},
        looked_up_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_get_cached_enrichment_returns_none_when_absent(engine):
    assert get_cached_enrichment(engine, "1.2.3.4", "abuseipdb") is None


def test_upsert_then_get_round_trips(engine):
    upsert_enrichment(engine, _result(), ttl_seconds=3600)

    view = get_cached_enrichment(engine, "1.2.3.4", "abuseipdb")

    assert view is not None
    assert view.indicator == "1.2.3.4"
    assert view.provider == "abuseipdb"
    assert view.verdict == "malicious"
    assert view.confidence == 90.0
    assert view.raw_response == {"some": "payload"}
    assert view.expires_at > view.looked_up_at


def test_upsert_overwrites_the_existing_row_for_the_same_indicator_and_provider(engine):
    upsert_enrichment(engine, _result(verdict="malicious", confidence=90.0), ttl_seconds=3600)
    upsert_enrichment(engine, _result(verdict="benign", confidence=5.0), ttl_seconds=3600)

    view = get_cached_enrichment(engine, "1.2.3.4", "abuseipdb")

    assert view.verdict == "benign"
    assert view.confidence == 5.0


def test_upsert_keeps_different_providers_for_the_same_indicator_independent(engine):
    upsert_enrichment(engine, _result(provider="abuseipdb", verdict="malicious"), ttl_seconds=3600)
    upsert_enrichment(engine, _result(provider="greynoise", verdict="benign"), ttl_seconds=3600)

    assert get_cached_enrichment(engine, "1.2.3.4", "abuseipdb").verdict == "malicious"
    assert get_cached_enrichment(engine, "1.2.3.4", "greynoise").verdict == "benign"


def test_upsert_keeps_different_indicators_for_the_same_provider_independent(engine):
    upsert_enrichment(engine, _result(indicator="1.1.1.1", verdict="benign"), ttl_seconds=3600)
    upsert_enrichment(engine, _result(indicator="6.6.6.6", verdict="malicious"), ttl_seconds=3600)

    assert get_cached_enrichment(engine, "1.1.1.1", "abuseipdb").verdict == "benign"
    assert get_cached_enrichment(engine, "6.6.6.6", "abuseipdb").verdict == "malicious"


def test_list_enrichments_for_indicators_returns_matches_across_providers(engine):
    upsert_enrichment(engine, _result(indicator="1.1.1.1", provider="abuseipdb"), ttl_seconds=3600)
    upsert_enrichment(engine, _result(indicator="1.1.1.1", provider="greynoise"), ttl_seconds=3600)
    upsert_enrichment(engine, _result(indicator="9.9.9.9", provider="abuseipdb"), ttl_seconds=3600)

    results = list_enrichments_for_indicators(engine, ["1.1.1.1"])

    assert {r.provider for r in results} == {"abuseipdb", "greynoise"}
    assert all(r.indicator == "1.1.1.1" for r in results)


def test_list_enrichments_for_indicators_empty_list_returns_empty(engine):
    upsert_enrichment(engine, _result(), ttl_seconds=3600)
    assert list_enrichments_for_indicators(engine, []) == []


def test_list_enrichments_for_indicators_ignores_unmatched_indicators(engine):
    upsert_enrichment(engine, _result(indicator="1.1.1.1"), ttl_seconds=3600)
    assert list_enrichments_for_indicators(engine, ["8.8.8.8"]) == []
