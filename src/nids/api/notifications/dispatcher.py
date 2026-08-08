"""Notification dispatcher: the sole subscriber to `MessageBus`'s
`"notifications"` channel, started as a background task in
`nids.api.app._lifespan` -- only if at least one channel is configured;
an app with none never subscribes, and publishing to a channel with zero
subscribers is a documented no-op on both `MessageBus` implementations
(see `bus.py`), so the publish side (`nids.api.notifications.publish`)
never needs to check whether anyone's listening.

Runs in-process for both the InMemoryBus and RedisBus tiers -- unlike
`nids.api.worker`'s live worker, which Streams/consumer-groups make
unsafe to also run in-process under RedisBus (see `worker.py`'s
docstring), `"notifications"` is plain Pub/Sub: every subscriber gets
every message, so there's no competing-consumer problem to avoid here.
The tradeoff this *does* introduce: if this API is ever run as multiple
replicas behind RedisBus, every replica's in-process dispatcher
subscribes independently, so every alert notifies once *per replica* --
a real limitation for horizontal scaling. Not a concern for this
project's documented single-instance deployment (`docs/DEPLOYMENT.md`),
but worth knowing before ever running multiple replicas with
notifications configured.
"""

from __future__ import annotations

import logging

from nids.api.alerts import Alert, NotificationChannel, alert_from_dict
from nids.api.bus import MessageBus
from nids.api.metrics import Metrics

logger = logging.getLogger(__name__)


async def dispatch_alert(
    alert: Alert, channels: list[NotificationChannel], metrics: Metrics | None = None
) -> None:
    """Calls every channel's `send`, independently -- one channel's
    failure (a downed webhook, an SMTP auth error) must never stop the
    others, and must never propagate to the caller: this always runs off
    the request path, so there is no caller left to usefully raise to."""
    for channel in channels:
        channel_name = type(channel).__name__
        try:
            channel.send(alert)
        except Exception:
            logger.exception(
                "Notification channel %s failed to send alert %s", channel_name, alert.alert_id
            )
            if metrics is not None:
                metrics.notifications_sent_total.labels(channel=channel_name, status="failure").inc()
        else:
            if metrics is not None:
                metrics.notifications_sent_total.labels(channel=channel_name, status="success").inc()


async def run_notification_dispatcher(
    bus: MessageBus, channels: list[NotificationChannel], metrics: Metrics | None = None
) -> None:
    """Runs forever, consuming the `"notifications"` channel one message
    at a time. A malformed message (should never happen -- the only
    publisher is `nids.api.notifications.publish.schedule_alert_publish`)
    is logged and dropped, the same "never take the loop down" rule
    `nids.api.worker.run_worker` follows for `"flows"`."""
    async for message in bus.subscribe("notifications"):
        try:
            alert = alert_from_dict(message)
        except (KeyError, ValueError):
            logger.exception("Dropping malformed notification message: %r", message)
            continue
        await dispatch_alert(alert, channels, metrics)
