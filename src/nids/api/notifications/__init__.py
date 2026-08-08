"""Notification channels (`nids.api.alerts.NotificationChannel`
implementations) plus the dispatcher that calls them. See
`docs/NOTIFICATIONS.md` for the full design and `nids.api.alerts` for the
`Alert` shape/severity-gating helpers every channel here consumes.
"""

from __future__ import annotations

from nids.api.alerts import NotificationChannel
from nids.api.config import ServingConfig
from nids.api.notifications.email_channel import EmailNotificationChannel
from nids.api.notifications.slack import SlackNotificationChannel


def build_channels(config: ServingConfig) -> list[NotificationChannel]:
    """Constructs every channel `config` has enough fields set for -- the
    Slack channel exists iff `slack_webhook_url` is set; the email
    channel iff `smtp_host`/`smtp_from_addr` and at least one
    `smtp_to_addrs` entry are all set. An app with neither configured
    gets an empty list, and `nids.api.app` never starts the notification
    dispatcher task in that case (see `nids.api.notifications.dispatcher`).
    """
    channels: list[NotificationChannel] = []
    if config.slack_webhook_url:
        channels.append(SlackNotificationChannel(config.slack_webhook_url))
    if config.smtp_host and config.smtp_from_addr and config.smtp_to_addrs:
        channels.append(
            EmailNotificationChannel(
                host=config.smtp_host,
                port=config.smtp_port,
                from_addr=config.smtp_from_addr,
                to_addrs=config.smtp_to_addrs,
                username=config.smtp_username,
                password=config.smtp_password,
                use_tls=config.smtp_use_tls,
            )
        )
    return channels
