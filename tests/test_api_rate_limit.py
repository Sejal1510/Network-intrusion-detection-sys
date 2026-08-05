import fakeredis
import pytest

from nids.api.rate_limit import InMemoryRateLimiter, RedisRateLimiter, create_rate_limiter

# ---------------------------------------------------------------------------
# InMemoryRateLimiter
# ---------------------------------------------------------------------------


async def test_inmemory_rate_limiter_allows_up_to_limit_within_window():
    limiter = InMemoryRateLimiter()

    results = [await limiter.allow("k", limit=3, window_seconds=60) for _ in range(3)]

    assert results == [True, True, True]


async def test_inmemory_rate_limiter_rejects_once_over_limit():
    limiter = InMemoryRateLimiter()

    for _ in range(3):
        await limiter.allow("k", limit=3, window_seconds=60)
    rejected = await limiter.allow("k", limit=3, window_seconds=60)

    assert rejected is False


async def test_inmemory_rate_limiter_tracks_separate_windows_per_key():
    limiter = InMemoryRateLimiter()

    for _ in range(3):
        await limiter.allow("a", limit=3, window_seconds=60)

    assert await limiter.allow("b", limit=3, window_seconds=60) is True


async def test_inmemory_rate_limiter_resets_after_window_rolls_over(monkeypatch):
    limiter = InMemoryRateLimiter()
    current_time = [1_000_000.0]
    monkeypatch.setattr("nids.api.rate_limit.time.time", lambda: current_time[0])

    for _ in range(3):
        await limiter.allow("k", limit=3, window_seconds=60)
    assert await limiter.allow("k", limit=3, window_seconds=60) is False

    current_time[0] += 61  # roll into the next window
    assert await limiter.allow("k", limit=3, window_seconds=60) is True


def test_create_rate_limiter_returns_inmemory_when_no_redis_url():
    assert isinstance(create_rate_limiter(None), InMemoryRateLimiter)


def test_create_rate_limiter_returns_redis_when_redis_url_set():
    assert isinstance(create_rate_limiter("redis://localhost:6379"), RedisRateLimiter)


# ---------------------------------------------------------------------------
# RedisRateLimiter (against fakeredis, no real Redis server needed)
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_redis_client():
    return fakeredis.FakeAsyncRedis(decode_responses=True)


async def test_redis_rate_limiter_allows_up_to_limit_within_window(fake_redis_client):
    limiter = RedisRateLimiter(client=fake_redis_client)

    results = [await limiter.allow("k", limit=3, window_seconds=60) for _ in range(3)]
    rejected = await limiter.allow("k", limit=3, window_seconds=60)

    assert results == [True, True, True]
    assert rejected is False


async def test_redis_rate_limiter_tracks_separate_windows_per_key(fake_redis_client):
    limiter = RedisRateLimiter(client=fake_redis_client)

    for _ in range(3):
        await limiter.allow("a", limit=3, window_seconds=60)

    assert await limiter.allow("b", limit=3, window_seconds=60) is True


async def test_redis_rate_limiter_resets_after_window_rolls_over(fake_redis_client, monkeypatch):
    limiter = RedisRateLimiter(client=fake_redis_client)
    current_time = [1_000_000.0]
    monkeypatch.setattr("nids.api.rate_limit.time.time", lambda: current_time[0])

    for _ in range(3):
        await limiter.allow("k", limit=3, window_seconds=60)
    assert await limiter.allow("k", limit=3, window_seconds=60) is False

    current_time[0] += 61
    assert await limiter.allow("k", limit=3, window_seconds=60) is True
