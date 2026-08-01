"""`PacketEvent`: the one packet-level primitive every capture source
(live NIC via `nids.agent.capture`, or a `.pcap` file via
`nids.flows.pcap`) produces. `FlowAggregator` (see `aggregator.py`)
consumes a stream of these and never needs to know where they came from.
"""

from __future__ import annotations

from dataclasses import dataclass

# Scapy TCP flag characters (matches Scapy's own `.sprintf("%TCP.flags%")`
# vocabulary): S=SYN, A=ACK, F=FIN, R=RST, P=PSH, U=URG, E=ECE, C=CWR.


@dataclass(frozen=True)
class PacketEvent:
    """One captured (or replayed-from-file) packet, reduced to exactly
    the fields flow aggregation needs -- never a raw payload."""

    timestamp: float
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    protocol: str  # "tcp" | "udp" | "icmp" | "other"
    length: int
    tcp_flags: str = ""  # e.g. "S", "SA", "A", "FA", "R" -- "" for non-TCP
    fragmented: bool = False  # IP fragmentation offset != 0
