"""Slack notification channel: posts a formatted message to an incoming
webhook URL (https://api.slack.com/messaging/webhooks) whenever an alert
meeting the configured minimum severity fires. `requests` is already a
dependency (`nids.agent.client`, `nids.data.download`) -- no new one
needed for this.
"""

from __future__ import annotations

import requests

from nids.api.alerts import Alert

_SEVERITY_EMOJI = {
    "low": ":large_blue_circle:",
    "medium": ":large_yellow_circle:",
    "high": ":large_orange_circle:",
    "critical": ":red_circle:",
}


class SlackNotificationChannel:
    """Implements `nids.api.alerts.NotificationChannel`. `webhook_url` is
    a Slack "Incoming Webhook" URL (created in Slack's own UI, one per
    workspace/channel) -- no Slack API token/OAuth scope involved."""

    def __init__(self, webhook_url: str, *, timeout_seconds: float = 5.0) -> None:
        self._webhook_url = webhook_url
        self._timeout_seconds = timeout_seconds

    def send(self, alert: Alert) -> None:
        emoji = _SEVERITY_EMOJI.get(alert.level, "")
        text = f"{emoji} *{alert.title}*\n{alert.message}"
        if alert.mitre is not None:
            techniques = ", ".join(f"{t.id} ({t.name})" for t in alert.mitre.techniques)
            text += f"\nMITRE ATT&CK: {alert.mitre.tactic} -- {techniques}"
        response = requests.post(
            self._webhook_url, json={"text": text}, timeout=self._timeout_seconds
        )
        response.raise_for_status()
