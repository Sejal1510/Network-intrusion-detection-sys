"""AbuseIPDB IP-reputation provider (https://docs.abuseipdb.com/#check-endpoint).
`requests` is already a dependency (`nids.api.notifications.slack`,
`nids.agent.client`) -- no new one needed for this.
"""

from __future__ import annotations

import requests

from nids.api.threat_intel import EnrichmentResult

_CHECK_URL = "https://api.abuseipdb.com/api/v2/check"


def _to_verdict(data: dict) -> str:
    if data.get("isWhitelisted"):
        return "benign"
    score = data.get("abuseConfidenceScore", 0)
    if score >= 75:
        return "malicious"
    if score >= 25:
        return "suspicious"
    if data.get("totalReports", 0) == 0:
        # Never reported at all -- genuinely no signal either way, distinct
        # from "reported, but with a low/zero confidence score" below.
        return "unknown"
    return "benign"


class AbuseIPDBProvider:
    """Implements `nids.api.threat_intel.ThreatIntelProvider`."""

    name = "abuseipdb"

    def __init__(self, api_key: str, *, timeout_seconds: float = 5.0) -> None:
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def lookup(self, indicator: str) -> EnrichmentResult:
        response = requests.get(
            _CHECK_URL,
            headers={"Key": self._api_key, "Accept": "application/json"},
            params={"ipAddress": indicator, "maxAgeInDays": 90},
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", {})
        return EnrichmentResult(
            indicator=indicator,
            provider=self.name,
            verdict=_to_verdict(data),
            # AbuseIPDB's own score is already 0-100 -- no rescaling needed,
            # unlike GreyNoise's Community tier (see greynoise.py).
            confidence=float(data.get("abuseConfidenceScore", 0)),
            raw_response=payload,
        )
