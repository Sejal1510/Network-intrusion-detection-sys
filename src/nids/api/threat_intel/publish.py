"""Producer side of the `"enrichment"` bus channel: called from
`nids.api.pipeline.finish_record`'s `enrich` callback (wired up in
`nids.api.app`/`nids.api.worker`) whenever an alert-worthy record carries
at least one routable IPv4 indicator. The consumer side is
`nids.api.threat_intel.dispatcher.run_enrichment_dispatcher`. Mirrors
`nids.api.notifications.publish` exactly -- same fire-and-forget
`run_coroutine_threadsafe` shape, same reasoning for why.
"""

from __future__ import annotations

import asyncio

from nids.api.bus import MessageBus


async def _publish_indicators(bus: MessageBus, indicators: list[str]) -> None:
    await bus.publish("enrichment", {"indicators": indicators})


def schedule_enrichment_publish(
    bus: MessageBus, loop: asyncio.AbstractEventLoop, indicators: list[str]
) -> None:
    """Fire-and-forget, safe to call from `/predict`'s synchronous
    threadpool thread or from the live worker's own event-loop thread --
    see `nids.api.notifications.publish.schedule_alert_publish`'s
    docstring, which this is a direct sibling of."""
    asyncio.run_coroutine_threadsafe(_publish_indicators(bus, indicators), loop)
