"""Threat-intelligence enrichment: looks up routable IPv4 indicators
(never NSL-KDD feature values, never ML/rule inputs) against external
reputation providers, purely as read-only context attached to an already-
made detection. Mirrors `nids.api.notifications`' shape closely --
`ThreatIntelProvider` is this module's `NotificationChannel`, `EnrichmentResult`
is its `Alert`, `build_providers` is its `build_channels` -- because the
same problem (a small set of interchangeable external integrations,
config-gated, individually non-fatal) has the same answer twice.

**Never influences detection.** `nids.api.risk`/`nids.api.alerts`/
`nids.api.rules` compute severity and fire alerts with zero awareness
this package exists; enrichment only ever runs *after* an alert has
already been generated (see `nids.api.pipeline.finish_record`), and its
only effect is a row in `nids.api.store`'s `ioc_enrichments` table a
dashboard can display alongside, never instead of, the ML/rule verdict.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

from nids.api.config import ServingConfig

# Deliberately a plain string tuple, not a Python Enum -- matches this
# codebase's existing convention for small fixed vocabularies (`severity`,
# `level`, `source`, `nids.api.user_auth.VALID_ROLES`) over a class hierarchy
# for what's really just a handful of string constants everyone reads/writes
# as plain strings (JSON payloads, SQL columns, frontend TS unions) anyway.
VALID_VERDICTS = ("malicious", "suspicious", "benign", "unknown")


@dataclass(frozen=True)
class EnrichmentResult:
    """One provider's answer for one indicator. `raw_response` keeps the
    full provider payload (the "relevant metadata" a dashboard or analyst
    may want beyond the normalized verdict/confidence) -- normalization
    below is deliberately lossy in the other direction, mapping each
    provider's own vocabulary onto `VALID_VERDICTS` so a dashboard can
    render AbuseIPDB and GreyNoise results identically without knowing
    either provider's API shape."""

    indicator: str
    provider: str
    verdict: str
    confidence: float  # 0-100, normalized per-provider -- see each adapter
    raw_response: dict[str, Any]
    looked_up_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.verdict not in VALID_VERDICTS:
            raise ValueError(f"verdict must be one of {VALID_VERDICTS!r}, got {self.verdict!r}")


class ThreatIntelProvider(Protocol):
    """Implemented by `nids.api.threat_intel.abuseipdb.AbuseIPDBProvider`
    and `nids.api.threat_intel.greynoise.GreyNoiseProvider`. `lookup`
    raises on any failure (network error, timeout, non-2xx status,
    malformed response) -- treating "no exception" as the only success
    signal, so the caller (`nids.api.threat_intel.dispatcher`) needs
    exactly one `except Exception` per provider call, the same breadth
    `nids.api.notifications.dispatcher.dispatch_alert` already uses for
    notification channels. Synchronous by design (plain `requests`, no
    new HTTP-client dependency) -- the dispatcher runs each call via
    `asyncio.to_thread` instead of requiring every provider to be
    async-native."""

    name: str

    def lookup(self, indicator: str) -> EnrichmentResult: ...


def is_routable_ipv4(value: str | None) -> bool:
    """`False` for anything that isn't a plain, public-routable IPv4
    address -- private (RFC1918), loopback, link-local, multicast,
    reserved, and unspecified addresses are all excluded, since querying
    an external reputation provider about e.g. `10.0.0.5` or `192.168.1.1`
    (a capture agent's own LAN, the overwhelmingly common case for lab/
    demo traffic) is meaningless and would just burn API quota on noise.
    IPv6 is out of scope for this milestone (see this package's module
    docstring) -- `ipaddress.ip_address` accepting an IPv6 literal is
    deliberately treated as "not routable *for us*" here, not an error."""
    if not value:
        return False
    try:
        addr = ipaddress.ip_address(value)
    except ValueError:
        return False
    if not isinstance(addr, ipaddress.IPv4Address):
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def extract_indicators(record: dict[str, Any]) -> list[str]:
    """The deduped, routable IPv4 indicators in a raw flow record --
    `src_ip`/`dst_ip`, present only when `nids.flows.aggregator.
    FlowAggregator` produced this record (see `store.PredictionRecord.
    src_ip`'s docstring); always empty for an API-sourced record, since
    NSL-KDD has no IP field to have supplied one at all."""
    candidates = (record.get("src_ip"), record.get("dst_ip"))
    seen: list[str] = []
    for value in candidates:
        if isinstance(value, str) and is_routable_ipv4(value) and value not in seen:
            seen.append(value)
    return seen


def build_providers(config: ServingConfig) -> list[ThreatIntelProvider]:
    """Constructs every provider `config` has an API key for -- an app
    with neither key set gets an empty list, and `nids.api.app` never
    starts the enrichment dispatcher task in that case (see
    `nids.api.threat_intel.dispatcher`), the same "unset = feature off,
    zero behavior change" convention `nids.api.notifications.build_channels`
    already establishes."""
    from nids.api.threat_intel.abuseipdb import AbuseIPDBProvider
    from nids.api.threat_intel.greynoise import GreyNoiseProvider

    providers: list[ThreatIntelProvider] = []
    if config.abuseipdb_api_key:
        providers.append(AbuseIPDBProvider(config.abuseipdb_api_key))
    if config.greynoise_api_key:
        providers.append(GreyNoiseProvider(config.greynoise_api_key))
    return providers
