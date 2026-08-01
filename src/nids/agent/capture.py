"""Live packet capture: wraps Scapy's `AsyncSniffer` to produce a
`PacketEvent` stream (see `nids.flows.schema`) -- the same primitive
`nids.flows.pcap` produces from a file, so `nids.flows.aggregator` never
needs to know which source fed it.

**Operational prerequisite** (documented, not solved here): live capture
needs elevated privileges -- Administrator + Npcap on Windows,
root/`CAP_NET_RAW` on Linux/Mac -- the same constraint `legacy/app.py`'s
own (now-superseded) live capture already documented.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any, Protocol

from scapy.sendrecv import AsyncSniffer

from nids.flows.scapy_adapter import to_packet_event
from nids.flows.schema import PacketEvent

logger = logging.getLogger(__name__)


class Capture(Protocol):
    """The surface `nids.agent.sources.LiveSource` depends on --
    `LiveCapture` (below) is the real implementation; tests inject a
    stub satisfying this instead, since real capture needs a live NIC
    and elevated privileges neither CI nor most development machines
    have on demand."""

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def events(self) -> AsyncIterator[PacketEvent]: ...


class LiveCapture:
    """Bridges Scapy's `AsyncSniffer` -- which delivers packets via a
    synchronous callback invoked from its own background thread -- into
    an `asyncio.Queue` this class's `events()` reads from. The standard
    thread-to-asyncio bridging pattern (`call_soon_threadsafe`).
    """

    def __init__(self, interface: str | None = None, bpf_filter: str | None = None) -> None:
        self._interface = interface
        self._bpf_filter = bpf_filter
        self._queue: asyncio.Queue[PacketEvent] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._sniffer: AsyncSniffer | None = None

    def _on_packet(self, pkt: Any) -> None:
        event = to_packet_event(pkt)
        if event is not None and self._loop is not None:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, event)

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._sniffer = AsyncSniffer(
            iface=self._interface, filter=self._bpf_filter, prn=self._on_packet, store=False
        )
        self._sniffer.start()
        logger.info("Live packet capture started on interface %r", self._interface or "default")

    def stop(self) -> None:
        if self._sniffer is not None:
            self._sniffer.stop()
            self._sniffer = None
            logger.info("Live packet capture stopped")

    async def events(self) -> AsyncIterator[PacketEvent]:
        while True:
            yield await self._queue.get()
