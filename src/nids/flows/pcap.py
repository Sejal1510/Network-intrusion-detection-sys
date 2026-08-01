"""Read a `.pcap`/`.pcapng` file into the same `PacketEvent` stream live
capture produces (see `nids.agent.capture`) -- reused by demo replay
(`nids.agent.sources`) and server-side PCAP upload (`nids.api.app`'s
`/predict/batch`). One extraction function, two callers: no duplicate
packet-parsing logic between "replay a file" and "upload a file."
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from scapy.layers.inet import ICMP, IP, TCP, UDP
from scapy.packet import Packet
from scapy.utils import PcapReader

from nids.flows.schema import PacketEvent


def _protocol_and_ports(pkt: Packet) -> tuple[str, int, int]:
    if pkt.haslayer(TCP):
        return "tcp", int(pkt[TCP].sport), int(pkt[TCP].dport)
    if pkt.haslayer(UDP):
        return "udp", int(pkt[UDP].sport), int(pkt[UDP].dport)
    if pkt.haslayer(ICMP):
        return "icmp", 0, 0
    return "other", 0, 0


def _to_packet_event(pkt: Packet) -> PacketEvent | None:
    if not pkt.haslayer(IP):
        return None  # non-IP traffic (ARP, etc.) carries no connection-level info

    protocol, src_port, dst_port = _protocol_and_ports(pkt)
    ip_layer = pkt[IP]
    tcp_flags = str(pkt[TCP].flags) if pkt.haslayer(TCP) else ""
    fragmented = ip_layer.frag != 0 or bool(ip_layer.flags.MF)

    return PacketEvent(
        timestamp=float(pkt.time),
        src_ip=ip_layer.src,
        dst_ip=ip_layer.dst,
        src_port=src_port,
        dst_port=dst_port,
        protocol=protocol,
        length=len(pkt),
        tcp_flags=tcp_flags,
        fragmented=fragmented,
    )


def iter_packet_events_from_pcap(path: str | Path) -> Iterator[PacketEvent]:
    """Yield a `PacketEvent` per IP packet in a `.pcap`/`.pcapng` file, in
    capture order. Non-IP packets (ARP, etc.) are skipped -- they carry
    no information this feature set uses. Streams the file (`PcapReader`)
    rather than loading it entirely into memory."""
    with PcapReader(str(path)) as reader:
        for pkt in reader:
            event = _to_packet_event(pkt)
            if event is not None:
                yield event
