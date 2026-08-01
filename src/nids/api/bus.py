"""MessageBus: the internal event transport between agent ingestion
(`nids.api.ingest`), the worker that runs the prediction pipeline
(`nids.api.worker`), and the WebSocket broadcast to dashboard clients
(`nids.api.broadcast`).

Two implementations behind one interface -- the same "swap the backend
without changing the interface" pattern `nids.api.store` already uses for
`database_url`:

- `InMemoryBus` (default, `redis_url=None`): `asyncio.Queue`-based. Zero
  new infrastructure -- how a single-process local/dev deployment runs;
  `create_app` runs the worker as a background task in the same process.
- `RedisBus` (opt-in, `redis_url` set): **Streams** for the `"flows"`
  (agent -> worker) channel -- durable, at-least-once, consumer-group
  scalable, so an agent's flow survives a worker restart. **Pub/Sub**
  for every other channel (dashboard fan-out) -- ephemeral, zero storage;
  a disconnected dashboard client catches up via the existing
  `nids.api.history` REST API, not via bus replay. Deliberately two
  different Redis primitives for two different reliability requirements,
  not one primitive reused everywhere.

This is the only module that imports `redis`, mirroring how
`nids.api.store` is the only module that imports `sqlalchemy`.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, Protocol


class MessageBus(Protocol):
    async def publish(self, channel: str, message: dict[str, Any]) -> None: ...

    def subscribe(self, channel: str) -> AsyncIterator[dict[str, Any]]: ...


class InMemoryBus:
    """`asyncio.Queue`-backed fan-out, scoped to one process. Each
    `subscribe` call gets its own queue; `publish` fans a message out to
    every currently-subscribed queue for that channel -- real Pub/Sub
    semantics: a subscriber that isn't listening yet doesn't receive
    messages published before it subscribed. Safe for this deployment
    tier because the worker (the "flows" channel's one subscriber)
    starts once at `create_app` time, before any agent can connect.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        for queue in self._subscribers.get(channel, []):
            queue.put_nowait(message)

    async def subscribe(self, channel: str) -> AsyncIterator[dict[str, Any]]:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(channel, []).append(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers[channel].remove(queue)


# Channels needing ingestion-grade durability (at-least-once, consumer
# groups). Every other channel (dashboard fan-out) uses Pub/Sub.
_STREAM_CHANNELS = frozenset({"flows"})


class RedisBus:
    """See module docstring: Streams for `"flows"`, Pub/Sub for
    everything else.

    `client` is a dependency-injection point like the rest of this
    platform's `df: pd.DataFrame | None = None` pattern: production
    callers leave it `None` (a real `redis.asyncio` client is built from
    `redis_url`); tests inject a `fakeredis.FakeAsyncRedis` instance
    directly, so `RedisBus` is fully testable without a real Redis
    server.
    """

    def __init__(
        self, redis_url: str | None = None, *, client: Any = None, consumer_group: str = "nids-workers"
    ) -> None:
        if client is not None:
            self._redis = client
        else:
            import redis.asyncio as redis_asyncio  # lazy: only paid for if actually used

            self._redis = redis_asyncio.from_url(redis_url, decode_responses=True)
        self._consumer_group = consumer_group
        self._consumer_name = f"consumer-{id(self)}"

    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        payload = json.dumps(message)
        if channel in _STREAM_CHANNELS:
            await self._redis.xadd(channel, {"data": payload})
        else:
            await self._redis.publish(channel, payload)

    async def subscribe(self, channel: str) -> AsyncIterator[dict[str, Any]]:
        if channel in _STREAM_CHANNELS:
            async for message in self._consume_stream(channel):
                yield message
        else:
            async for message in self._consume_pubsub(channel):
                yield message

    async def _consume_stream(self, channel: str) -> AsyncIterator[dict[str, Any]]:
        from redis.exceptions import ResponseError

        try:
            await self._redis.xgroup_create(channel, self._consumer_group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

        while True:
            response = await self._redis.xreadgroup(
                self._consumer_group,
                self._consumer_name,
                {channel: ">"},
                count=10,
                block=1000,
            )
            for _stream_name, entries in response:
                for entry_id, fields in entries:
                    yield json.loads(fields["data"])
                    await self._redis.xack(channel, self._consumer_group, entry_id)

    async def _consume_pubsub(self, channel: str) -> AsyncIterator[dict[str, Any]]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield json.loads(message["data"])
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()


def create_bus(redis_url: str | None) -> MessageBus:
    """`redis_url=None` (the default) -> `InMemoryBus`; set -> `RedisBus`.
    The one place this decision is made."""
    if redis_url is None:
        return InMemoryBus()
    return RedisBus(redis_url)
