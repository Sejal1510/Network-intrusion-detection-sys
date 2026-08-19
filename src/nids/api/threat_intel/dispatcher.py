"""Enrichment dispatcher: the sole subscriber to `MessageBus`'s
`"enrichment"` channel, started as a background task in
`nids.api.app._lifespan` -- only if at least one provider is configured
*and* a database is configured (the cache lives there; see
`nids.api.store.IocEnrichmentRecord`). Mirrors
`nids.api.notifications.dispatcher` closely, with one deliberate
difference: see `dispatch_enrichment`'s docstring for why provider calls
run via `asyncio.to_thread` here instead of inline.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.engine import Engine

from nids.api.bus import MessageBus
from nids.api.metrics import Metrics
from nids.api.store import get_cached_enrichment, upsert_enrichment
from nids.api.threat_intel import ThreatIntelProvider

logger = logging.getLogger(__name__)


async def dispatch_enrichment(
    indicators: list[str],
    providers: list[ThreatIntelProvider],
    cache_ttl_seconds: int,
    db_engine: Engine,
    metrics: Metrics | None = None,
) -> None:
    """For each indicator x provider: skip if a still-fresh cache entry
    already exists, otherwise call the provider and cache the result. One
    provider's failure (timeout, rate limit, outage) never stops another
    and never propagates -- this always runs off the request/live-worker
    path, so there is no caller left to usefully raise to (same reasoning
    `nids.api.notifications.dispatcher.dispatch_alert` already documents).

    Each provider call runs via `await asyncio.to_thread(provider.lookup,
    indicator)`, not inline the way `dispatch_alert` calls
    `channel.send(alert)` directly. That's a deliberate difference, not
    an inconsistency: the notification dispatcher blocking the shared
    event loop for one `requests.post` is an accepted, low-volume
    tradeoff there, but this dispatcher's caller
    (`nids.api.pipeline.finish_record`, reached from *both* `/predict`'s
    threadpool and the live worker's own event-loop task) has an explicit
    "never block live capture" requirement -- and the live worker runs on
    this exact loop, so a blocking call here would delay every flow
    behind it, not just this one. `asyncio.to_thread` needs no new
    dependency (`requests` already is one) and keeps every
    `ThreatIntelProvider` implementation a plain synchronous function.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # naive: matches
    # how SQLite/SQLAlchemy round-trips DateTime columns -- see
    # nids.api.user_auth.authenticate_session's identical comment.
    for indicator in indicators:
        for provider in providers:
            cached = get_cached_enrichment(db_engine, indicator, provider.name)
            if cached is not None and cached.expires_at > now:
                continue
            try:
                result = await asyncio.to_thread(provider.lookup, indicator)
            except Exception:
                logger.warning(
                    "Threat-intel provider %s failed to enrich %s",
                    provider.name,
                    indicator,
                    exc_info=True,
                )
                if metrics is not None:
                    metrics.ioc_enrichment_lookups_total.labels(
                        provider=provider.name, status="failure"
                    ).inc()
                continue
            upsert_enrichment(db_engine, result, cache_ttl_seconds)
            if metrics is not None:
                metrics.ioc_enrichment_lookups_total.labels(
                    provider=provider.name, status="success"
                ).inc()


async def run_enrichment_dispatcher(
    bus: MessageBus,
    providers: list[ThreatIntelProvider],
    cache_ttl_seconds: int,
    db_engine: Engine,
    metrics: Metrics | None = None,
) -> None:
    """Runs forever, consuming the `"enrichment"` channel one message at
    a time. A malformed message (should never happen -- the only
    publisher is `nids.api.threat_intel.publish.schedule_enrichment_publish`)
    is logged and dropped, the same "never take the loop down" rule
    `nids.api.worker.run_worker`/`nids.api.notifications.dispatcher.
    run_notification_dispatcher` already follow."""
    async for message in bus.subscribe("enrichment"):
        indicators = message.get("indicators")
        if not isinstance(indicators, list) or not all(isinstance(i, str) for i in indicators):
            logger.exception("Dropping malformed enrichment message: %r", message)
            continue
        await dispatch_enrichment(indicators, providers, cache_ttl_seconds, db_engine, metrics)
