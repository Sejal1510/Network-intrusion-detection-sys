"""Alert engine: threshold-gated, pure -- turns a `RiskScore` that
crosses `ALERT_THRESHOLD` into an `Alert` a SOC analyst (or a
notification channel, see `nids.api.notifications`) can act on.

Most predictions should *not* become alerts; a SOC screaming about every
normal packet is useless. `generate_alert` returning `None` below
threshold is the common, expected outcome, not a missing case.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from nids.api.explain import Explanation
from nids.api.inference import PredictionResult
from nids.api.mitre import MitreMapping, MitreTechnique
from nids.api.risk import RiskScore

DEFAULT_ALERT_THRESHOLD = 70.0

# Same ordering `nids.api.risk._SEVERITY_BANDS` encodes numerically, kept
# as a small local list rather than importing that private constant --
# this is a notification-policy concern (nids.api.notifications), not a
# risk-scoring one.
_SEVERITY_ORDER = ("low", "medium", "high", "critical")


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
    """Implemented by `nids.api.notifications.slack.SlackNotificationChannel`
    and `nids.api.notifications.email_channel.EmailNotificationChannel`;
    `nids.api.notifications.dispatcher.run_notification_dispatcher` calls
    every configured channel whenever an `Alert` meeting the configured
    minimum severity (see `meets_min_severity` below) is raised. `Alert`
    is a plain, serializable dataclass any channel can format -- nothing
    here needs to change to add a new one (e.g. Teams)."""

    def send(self, alert: Alert) -> None: ...


def meets_min_severity(level: str, minimum: str) -> bool:
    """Whether `level` is at or above `minimum` in `_SEVERITY_ORDER` --
    the notification-dispatch gate, kept separate from
    `generate_alert`'s own `threshold`: not every alert (a SOC-worthy
    event) should page someone (a human-interruptive one). Both default
    to their most permissive setting independently -- see
    `ServingConfig.notification_min_severity`."""
    return _SEVERITY_ORDER.index(level) >= _SEVERITY_ORDER.index(minimum)


def severity_rank(level: str) -> int:
    """0 (low) .. 3 (critical) -- for comparing severities, e.g. picking
    the higher-severity `Alert` when both the ML path (`generate_alert`)
    and a signature match (`nids.api.rules.evaluate_rules`) fire for the
    same record (see `nids.api.pipeline.finish_record`)."""
    return _SEVERITY_ORDER.index(level)


def alert_to_dict(alert: Alert) -> dict[str, Any]:
    """`Alert` -> a JSON-safe dict, for publishing on
    `nids.api.bus.MessageBus`'s `"notifications"` channel (which, like
    every non-`"flows"` channel, carries plain dicts -- see `bus.py`).
    Mirrors the `dataclasses.asdict` convention `nids.api.store` already
    uses for `MitreMapping`/`Explanation`, plus explicit `datetime`
    handling since JSON has no native datetime type."""
    return {
        "alert_id": alert.alert_id,
        "created_at": alert.created_at.isoformat(),
        "level": alert.level,
        "title": alert.title,
        "message": alert.message,
        "risk_score": alert.risk_score,
        "attack_category": alert.attack_category,
        "mitre": (
            {
                "tactic": alert.mitre.tactic,
                "techniques": [
                    {"id": t.id, "name": t.name, "url": t.url} for t in alert.mitre.techniques
                ],
            }
            if alert.mitre is not None
            else None
        ),
        "source": alert.source,
    }


def alert_from_dict(data: dict[str, Any]) -> Alert:
    """Inverse of `alert_to_dict` -- reconstructs the `Alert` a
    notification channel's `send(alert: Alert)` expects from the dict a
    `"notifications"`-channel subscriber (`nids.api.notifications.
    dispatcher`) actually receives off the bus."""
    mitre_data = data["mitre"]
    mitre = (
        MitreMapping(
            tactic=mitre_data["tactic"],
            techniques=[MitreTechnique(**t) for t in mitre_data["techniques"]],
        )
        if mitre_data is not None
        else None
    )
    return Alert(
        alert_id=data["alert_id"],
        created_at=datetime.fromisoformat(data["created_at"]),
        level=data["level"],
        title=data["title"],
        message=data["message"],
        risk_score=data["risk_score"],
        attack_category=data["attack_category"],
        mitre=mitre,
        source=data["source"],
    )


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
