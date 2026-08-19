"""GreyNoise IP-context provider, Community API tier
(https://docs.greynoise.io/reference/get_v3-community-ip). `requests` is
already a dependency -- see `abuseipdb.py`'s module docstring.
"""

from __future__ import annotations

import requests

from nids.api.threat_intel import EnrichmentResult

_BASE_URL = "https://api.greynoise.io/v3/community"

# GreyNoise's Community tier already returns a `classification` field in
# almost exactly this vocabulary ("malicious"/"benign"/"unknown", never
# "suspicious") -- so unlike AbuseIPDB, there's no score-bucketing to do,
# just a pass-through with a validity fallback. It has no numeric
# confidence field at all, so this is a deterministic mapping *we* define
# (documented, not fabricated provider data) rather than anything GreyNoise
# itself asserts a number for.
_CONFIDENCE_BY_VERDICT = {"malicious": 90.0, "benign": 10.0, "unknown": 0.0}


def _to_verdict(classification: str | None) -> str:
    return classification if classification in _CONFIDENCE_BY_VERDICT else "unknown"


class GreyNoiseProvider:
    """Implements `nids.api.threat_intel.ThreatIntelProvider`."""

    name = "greynoise"

    def __init__(self, api_key: str, *, timeout_seconds: float = 5.0) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def lookup(self, indicator: str) -> EnrichmentResult:
        response = requests.get(
            f"{_BASE_URL}/{indicator}",
            headers={"key": self._api_key, "Accept": "application/json"},
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        verdict = _to_verdict(payload.get("classification"))
        return EnrichmentResult(
            indicator=indicator,
            provider=self.name,
            verdict=verdict,
            confidence=_CONFIDENCE_BY_VERDICT[verdict],
            raw_response=payload,
        )
