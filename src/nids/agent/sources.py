"""`FlowSource`: the seam between "where flow records come from" and "how
they're sent" (`nids.agent.client`). `LiveSource` wraps live packet
capture + flow aggregation; `ReplaySource` (see this module) reads a
saved `.pcap` or dataset instead -- the client doesn't know or care
which, and neither duplicates the other's downstream handling.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any, Protocol

from nids.agent.capture import Capture, LiveCapture
from nids.flows.aggregator import FlowAggregator
from nids.flows.pcap import iter_packet_events_from_pcap
from nids.flows.schema import PacketEvent


class FlowSource(Protocol):
    def records(self) -> AsyncIterator[dict[str, Any]]: ...


class LiveSource:
    """Live capture -> `FlowAggregator` -> raw records satisfying
    `FEATURE_COLUMNS` exactly like every other input path. `capture` is a
    dependency-injection point (matching this project's `df: pd.DataFrame
    | None = None` pattern elsewhere): production callers leave it
    `None` (a real `LiveCapture`, needing elevated privileges); tests
    inject a stub `Capture`.
    """

    def __init__(
        self,
        interface: str | None = None,
        bpf_filter: str | None = None,
        flush_interval: float = 2.0,
        capture: Capture | None = None,
    ) -> None:
        self._capture: Capture = capture if capture is not None else LiveCapture(interface, bpf_filter)
        self._aggregator = FlowAggregator()
        self._flush_interval = flush_interval

    async def records(self) -> AsyncIterator[dict[str, Any]]:
        self._capture.start()
        event_stream = self._capture.events()
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        event_stream.__anext__(), timeout=self._flush_interval
                    )
                except TimeoutError:
                    event = None

                if event is not None:
                    record = self._aggregator.process_packet(event)
                    if record is not None:
                        yield record

                now = event.timestamp if event is not None else time.time()
                for flushed in self._aggregator.flush_idle(now):
                    yield flushed
        finally:
            self._capture.stop()


class ReplaySource:
    """Replays a saved `.pcap` file through the *same* `FlowAggregator`
    `LiveSource` uses -- reused, not reimplemented -- at a configurable
    pace: `speed=1.0` reproduces the capture's own inter-arrival timing;
    higher values accelerate it (useful for a live demo/presentation);
    `speed=None` replays as fast as possible (useful for CI/tests, which
    need neither root privileges nor real traffic to exercise the full
    live pipeline).
    """

    def __init__(self, pcap_path: str | Path, speed: float | None = 1.0) -> None:
        self._pcap_path = pcap_path
        self._speed = speed
        self._aggregator = FlowAggregator()

    def _events(self) -> Iterator[PacketEvent]:
        return iter_packet_events_from_pcap(self._pcap_path)

    async def records(self) -> AsyncIterator[dict[str, Any]]:
        previous_timestamp: float | None = None
        for event in self._events():
            if self._speed is not None and previous_timestamp is not None:
                delay = (event.timestamp - previous_timestamp) / self._speed
                if delay > 0:
                    await asyncio.sleep(delay)
            previous_timestamp = event.timestamp

            record = self._aggregator.process_packet(event)
            if record is not None:
                yield record

        for flushed in self._aggregator.flush_idle(time.time()):
            yield flushed
