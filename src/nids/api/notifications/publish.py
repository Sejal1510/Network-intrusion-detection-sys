"""Producer side of the `"notifications"` bus channel: called from
`nids.api.pipeline.finish_record`'s `notify` callback (wired up in
`nids.api.app`/`nids.api.worker`) whenever an alert meeting the
configured minimum severity fires. The consumer side is
`nids.api.notifications.dispatcher.run_notification_dispatcher`.
"""

from __future__ import annotations

import asyncio

from nids.api.alerts import Alert, alert_to_dict
from nids.api.bus import MessageBus


async def _publish_alert(bus: MessageBus, alert: Alert) -> None:
    await bus.publish("notifications", alert_to_dict(alert))


def schedule_alert_publish(bus: MessageBus, loop: asyncio.AbstractEventLoop, alert: Alert) -> None:
    """Fire-and-forget: schedules the publish onto `loop` and returns
    immediately, without awaiting the result. Safe to call from a plain
    sync function running in FastAPI's threadpool -- `/predict` is
    intentionally a synchronous route (see `nids.api.app`), since model
    inference is CPU-bound, not I/O-bound; making it `async def` would
    block the event loop instead of freeing it -- via
    `run_coroutine_threadsafe`, and equally safe to call from `loop`'s
    own thread (`nids.api.worker`'s already-async path does), since
    `run_coroutine_threadsafe` supports both. The scheduled coroutine's
    result/exception is deliberately never awaited or retrieved: a
    `MessageBus.publish` failure here has nothing meaningful to
    propagate to -- the HTTP response already reflects a successful
    prediction, alert generation included; only whether it got
    *published for notification*, a best-effort side channel, could
    fail."""
    asyncio.run_coroutine_threadsafe(_publish_alert(bus, alert), loop)
