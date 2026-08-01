import asyncio

import fakeredis
import pytest

from nids.api.bus import InMemoryBus, RedisBus, create_bus

# ---------------------------------------------------------------------------
# InMemoryBus
# ---------------------------------------------------------------------------


async def test_inmemory_bus_delivers_published_message_to_subscriber():
    bus = InMemoryBus()

    async def consume():
        async for message in bus.subscribe("test"):
            return message

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)  # let the subscriber generator start and register its queue

    await bus.publish("test", {"hello": "world"})

    result = await asyncio.wait_for(task, timeout=1)
    assert result == {"hello": "world"}


async def test_inmemory_bus_fans_out_to_every_subscriber():
    bus = InMemoryBus()
    received = []

    async def consume(name):
        async for message in bus.subscribe("test"):
            received.append((name, message))
            return

    task_a = asyncio.create_task(consume("a"))
    task_b = asyncio.create_task(consume("b"))
    await asyncio.sleep(0)

    await bus.publish("test", {"n": 1})
    await asyncio.wait_for(asyncio.gather(task_a, task_b), timeout=1)

    assert len(received) == 2
    assert {name for name, _ in received} == {"a", "b"}


async def test_inmemory_bus_drops_messages_published_before_any_subscriber():
    bus = InMemoryBus()
    await bus.publish("test", {"missed": True})  # no subscriber yet -- dropped

    subscription = bus.subscribe("test")
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(subscription.__anext__(), timeout=0.05)


async def test_inmemory_bus_cleans_up_queue_on_unsubscribe():
    bus = InMemoryBus()

    async def consume_one():
        async for _ in bus.subscribe("test"):
            return

    task = asyncio.create_task(consume_one())
    await asyncio.sleep(0)
    assert len(bus._subscribers["test"]) == 1

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(bus._subscribers["test"]) == 0


def test_create_bus_returns_inmemory_bus_when_no_redis_url():
    assert isinstance(create_bus(None), InMemoryBus)


def test_create_bus_returns_redis_bus_when_redis_url_set():
    assert isinstance(create_bus("redis://localhost:6379"), RedisBus)


# ---------------------------------------------------------------------------
# RedisBus (against fakeredis, no real Redis server needed)
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_redis_client():
    return fakeredis.FakeAsyncRedis(decode_responses=True)


async def test_redis_bus_pubsub_channel_roundtrip(fake_redis_client):
    bus = RedisBus(client=fake_redis_client)

    async def consume():
        async for message in bus.subscribe("live"):
            return message

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)  # let the pubsub subscription actually register

    await bus.publish("live", {"prediction": "attack"})

    result = await asyncio.wait_for(task, timeout=2)
    assert result == {"prediction": "attack"}


async def test_redis_bus_stream_channel_delivers_and_acks(fake_redis_client):
    bus = RedisBus(client=fake_redis_client)

    await bus.publish("flows", {"duration": 0, "service": "http"})

    subscription = bus.subscribe("flows")
    message = await asyncio.wait_for(subscription.__anext__(), timeout=2)

    assert message == {"duration": 0, "service": "http"}


async def test_redis_bus_stream_does_not_redeliver_acked_messages(fake_redis_client):
    bus = RedisBus(client=fake_redis_client)
    await bus.publish("flows", {"n": 1})

    subscription = bus.subscribe("flows")
    first = await asyncio.wait_for(subscription.__anext__(), timeout=2)
    assert first == {"n": 1}

    await bus.publish("flows", {"n": 2})
    second = await asyncio.wait_for(subscription.__anext__(), timeout=2)
    assert second == {"n": 2}  # not a redelivery of {"n": 1}


async def test_redis_bus_stream_consumer_group_creation_is_idempotent(fake_redis_client):
    bus = RedisBus(client=fake_redis_client)
    await bus.publish("flows", {"n": 1})

    subscription_a = bus.subscribe("flows")
    await asyncio.wait_for(subscription_a.__anext__(), timeout=2)  # creates the group

    bus2 = RedisBus(client=fake_redis_client)
    await bus2.publish("flows", {"n": 2})
    subscription_b = bus2.subscribe("flows")
    result = await asyncio.wait_for(subscription_b.__anext__(), timeout=2)  # must not raise BUSYGROUP

    assert result == {"n": 2}
