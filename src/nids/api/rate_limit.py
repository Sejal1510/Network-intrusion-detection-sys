"""RateLimiter: per-client-IP request throttling for the two currently-
unauthenticated route groups an attacker could otherwise hammer for free --
device pairing (`nids.api.ingest`: POST /agent/pair, POST /agent/pair/exchange
-- see docs/DASHBOARD.md's previously-flagged "no rate limit or auth" gap)
and inference (`nids.api.app`: POST /predict, POST /predict/batch).

Same "swap the backend without changing the interface" pattern
`nids.api.bus`/`nids.api.store` already use for `redis_url`/`database_url`:

- `InMemoryRateLimiter` (default, `redis_url=None`): a plain dict, scoped to
  one process -- fine for the single-process/no-Redis deployment tier every
  other in-memory default here already targets.
- `RedisRateLimiter` (opt-in, `redis_url` set): shared counters across every
  API process behind a load balancer -- otherwise each process enforces its
  own independent limit, silently multiplying the effective limit by
  process count. Reuses `ServingConfig.redis_url` -- the same connection
  string `nids.api.bus` already uses -- rather than a second Redis config
  field; a deployment that scales to multiple processes needs Redis for
  both the bus and the rate limiter at once, not one or the other.

**Fixed window counter**, not sliding window or token bucket: increment a
per-`(key, window)` counter, reset it when the window rolls over. The
simplest of the three that's still a real bound -- exactly `limit`
requests per `window_seconds`, forever, per key. Its one known imprecision
(a client can burst up to ~2x `limit` by timing requests around a window
boundary) is irrelevant here: these are abuse backstops for two specific,
named gaps, not a billing-grade throughput guarantee, so the extra
bookkeeping a sliding window or token bucket needs isn't worth it.

This is the only module (besides `nids.api.bus`) that imports `redis`.
"""

from __future__ import annotations

import time
from typing import Any, Protocol


class RateLimiter(Protocol):
    async def allow(self, key: str, *, limit: int, window_seconds: int) -> bool: ...


class InMemoryRateLimiter:
    """dict-backed fixed-window counters, scoped to one process. No lock
    needed: FastAPI/uvicorn's default single-worker event loop means
    `allow` never actually runs concurrently with itself."""

    def __init__(self) -> None:
        self._counts: dict[str, tuple[int, int]] = {}  # key -> (window_index, count)

    async def allow(self, key: str, *, limit: int, window_seconds: int) -> bool:
        window_index = int(time.time() // window_seconds)
        stored_window, count = self._counts.get(key, (window_index, 0))
        if stored_window != window_index:
            stored_window, count = window_index, 0
        count += 1
        self._counts[key] = (stored_window, count)
        return count <= limit


class RedisRateLimiter:
    """Fixed-window counters shared across every process pointed at the same
    Redis -- `INCR` on a per-`(key, window)` Redis key, `EXPIRE`d so stale
    windows self-clean instead of accumulating forever. `client` is the same
    dependency-injection point `nids.api.bus.RedisBus` already uses: `None`
    in production (a real `redis.asyncio` client built from `redis_url`), a
    `fakeredis.FakeAsyncRedis` in tests."""

    def __init__(self, redis_url: str | None = None, *, client: Any = None) -> None:
        if client is not None:
            self._redis = client
        else:
            import redis.asyncio as redis_asyncio  # lazy: only paid for if actually used

            self._redis = redis_asyncio.from_url(redis_url, decode_responses=True)

    async def allow(self, key: str, *, limit: int, window_seconds: int) -> bool:
        window_index = int(time.time() // window_seconds)
        redis_key = f"ratelimit:{key}:{window_index}"
        count = await self._redis.incr(redis_key)
        if count == 1:
            await self._redis.expire(redis_key, window_seconds)
        return count <= limit


def create_rate_limiter(redis_url: str | None) -> RateLimiter:
    """`redis_url=None` (the default) -> `InMemoryRateLimiter`; set ->
    `RedisRateLimiter`. The one place this decision is made."""
    if redis_url is None:
        return InMemoryRateLimiter()
    return RedisRateLimiter(redis_url)
