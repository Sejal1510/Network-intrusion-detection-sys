import asyncio
import time
from pathlib import Path

import pytest

from nids.agent.sources import LiveSource, ReplaySource
from nids.data.schema import FEATURE_COLUMNS
from nids.flows.schema import PacketEvent

PCAP_FIXTURE = Path(__file__).parent / "fixtures" / "sample_capture.pcap"


class _FakeCapture:
    """A stub `Capture` (see `nids.agent.capture.Capture`) -- production
    `LiveSource` uses a real `LiveCapture`, needing elevated privileges
    and a live NIC neither CI nor most dev machines grant on demand."""

    def __init__(self, events: list[PacketEvent]):
        self._events = events
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    async def events(self):
        for event in self._events:
            yield event
        # Real Capture.events() is an infinite stream (blocks on the
        # queue forever) -- match that contract rather than raising
        # StopAsyncIteration once the fixture's own events run out;
        # a caller stops consuming by cancelling, as these tests do.
        await asyncio.Event().wait()


def _pkt(t, src_ip, src_port, dst_ip, dst_port, protocol="tcp", flags="", length=60):
    return PacketEvent(
        timestamp=t,
        src_ip=src_ip,
        dst_ip=dst_ip,
        src_port=src_port,
        dst_port=dst_port,
        protocol=protocol,
        length=length,
        tcp_flags=flags,
    )


async def test_live_source_yields_records_from_completed_connections():
    events = [
        _pkt(0.0, "10.0.0.1", 5000, "9.9.9.9", 80, flags="S"),
        _pkt(0.1, "9.9.9.9", 80, "10.0.0.1", 5000, flags="R"),  # REJ -- completes immediately
    ]
    source = LiveSource(capture=_FakeCapture(events), flush_interval=5.0)

    records = []
    async for record in source.records():
        records.append(record)
        if len(records) == 1:
            break

    assert len(records) == 1
    assert set(records[0].keys()) == set(FEATURE_COLUMNS)
    assert records[0]["flag"] == "REJ"


async def test_live_source_starts_and_stops_the_capture():
    events = [_pkt(0.0, "10.0.0.1", 5000, "9.9.9.9", 80, flags="S")]
    fake_capture = _FakeCapture(events)
    source = LiveSource(capture=fake_capture, flush_interval=5.0)

    with pytest.raises(TimeoutError):

        async def _consume():
            async for _ in source.records():
                pass  # never completes on its own -- REJ never arrives, only idle-flush would end it

        await asyncio.wait_for(_consume(), timeout=0.2)

    assert fake_capture.started is True
    assert fake_capture.stopped is True  # stopped via the `finally` even after being cancelled


async def test_replay_source_reproduces_the_same_records_as_direct_aggregation():
    """Reused, not reimplemented: ReplaySource's output must match what
    the same FlowAggregator produces when fed directly (see
    test_flows_pcap.py)."""
    source = ReplaySource(PCAP_FIXTURE, speed=None)  # no delay -- fast for tests

    records = [record async for record in source.records()]

    assert len(records) >= 1
    tcp_records = [r for r in records if r["protocol_type"] == "tcp"]
    assert tcp_records[0]["flag"] == "SF"
    assert tcp_records[0]["service"] == "http"


async def test_replay_source_records_satisfy_feature_columns_contract():
    source = ReplaySource(PCAP_FIXTURE, speed=None)

    records = [record async for record in source.records()]

    for record in records:
        assert set(record.keys()) == set(FEATURE_COLUMNS)


async def test_replay_source_respects_speed_pacing():
    source = ReplaySource(PCAP_FIXTURE, speed=1000.0)  # accelerated, but not instant

    start = time.monotonic()
    async for _ in source.records():
        pass
    elapsed = time.monotonic() - start

    assert elapsed < 1.0  # the fixture spans 0.4s of capture time / 1000x speed -- must finish fast
