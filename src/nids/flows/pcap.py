"""Read a `.pcap`/`.pcapng` file into the same `PacketEvent` stream live
capture produces (see `nids.agent.capture`) -- reused by demo replay
(`nids.agent.sources`) and server-side PCAP upload (`nids.api.app`'s
`/predict/batch`). One extraction function, two callers: no duplicate
packet-parsing logic between "replay a file" and "upload a file."
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from scapy.utils import PcapReader

from nids.flows.scapy_adapter import to_packet_event
from nids.flows.schema import PacketEvent


def iter_packet_events_from_pcap(path: str | Path) -> Iterator[PacketEvent]:
    """Yield a `PacketEvent` per IP packet in a `.pcap`/`.pcapng` file, in
    capture order. Non-IP packets (ARP, etc.) are skipped -- they carry
    no information this feature set uses. Streams the file (`PcapReader`)
    rather than loading it entirely into memory."""
    with PcapReader(str(path)) as reader:
        for pkt in reader:
            event = to_packet_event(pkt)
            if event is not None:
                yield event
