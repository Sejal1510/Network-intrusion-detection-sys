"""Alert engine: threshold-gated, pure -- turns a `RiskScore` that
crosses `ALERT_THRESHOLD` into an `Alert` a SOC analyst (or, later, a
notification channel) can act on.

Most predictions should *not* become alerts; a SOC screaming about every
normal packet is useless. `generate_alert` returning `None` below
threshold is the common, expected outcome, not a missing case.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from nids.api.explain import Explanation
from nids.api.inference import PredictionResult
from nids.api.mitre import MitreMapping
from nids.api.risk import RiskScore

DEFAULT_ALERT_THRESHOLD = 70.0


@dataclass(frozen=True)
class Alert:
    alert_id: str
    created_at: datetime
    level: str  # == RiskScore.severity -- reused, not a second taxonomy
    title: str
    message: str
    risk_score: float
    attack_category: str | None
    mitre: MitreMapping | None
    source: str  # "api" for now; future: "live_capture", "batch_upload"


class NotificationChannel(Protocol):
    """Future extension point (not implemented): a notification channel
    (email/Slack/Teams/...) implements `send`, and a future dispatcher
    calls every configured channel whenever `generate_alert` returns a
    non-`None` `Alert`. `Alert` is already a plain, serializable
    dataclass any channel can format -- nothing here needs to change to
    add one."""

    def send(self, alert: Alert) -> None: ...


def _build_message(
    result: PredictionResult, risk_score: RiskScore, explanation: Explanation | None
) -> str:
    subject = result.attack_category or "activity"
    message = (
        f"{risk_score.severity.upper()} risk {subject} detected "
        f"(score {risk_score.score:.0f}/100)"
    )
    if explanation is not None:
        message = f"{message}. {explanation.summary}"
    return message


def generate_alert(
    result: PredictionResult,
    risk_score: RiskScore,
    mitre: MitreMapping | None,
    explanation: Explanation | None = None,
    threshold: float = DEFAULT_ALERT_THRESHOLD,
    source: str = "api",
) -> Alert | None:
    """Build an `Alert` if `risk_score.score >= threshold`, else `None`.

    `mitre`/`explanation` are consumed only to enrich the alert's fields
    and message -- neither is recomputed here; both are whatever the
    caller already produced via `nids.api.mitre`/`nids.api.explain`.
    """
    if risk_score.score < threshold:
        return None

    return Alert(
        alert_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        level=risk_score.severity,
        title=f"{risk_score.severity.capitalize()} risk detected",
        message=_build_message(result, risk_score, explanation),
        risk_score=risk_score.score,
        attack_category=result.attack_category,
        mitre=mitre,
        source=source,
    )
