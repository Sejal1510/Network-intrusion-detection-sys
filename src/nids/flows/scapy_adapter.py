"""Scapy `Packet` -> `PacketEvent`: the one conversion function every
Scapy-based packet source uses, whether the packets came from a `.pcap`
file (`nids.flows.pcap`) or a live interface (`nids.agent.capture`).
Extracted here specifically so those two modules don't each carry their
own copy of the same field-mapping logic.
"""

from __future__ import annotations

from scapy.layers.inet import ICMP, IP, TCP, UDP
from scapy.packet import Packet

from nids.flows.schema import PacketEvent


def _protocol_and_ports(pkt: Packet) -> tuple[str, int, int]:
    if pkt.haslayer(TCP):
        return "tcp", int(pkt[TCP].sport), int(pkt[TCP].dport)
    if pkt.haslayer(UDP):
        return "udp", int(pkt[UDP].sport), int(pkt[UDP].dport)
    if pkt.haslayer(ICMP):
        return "icmp", 0, 0
    return "other", 0, 0


def to_packet_event(pkt: Packet) -> PacketEvent | None:
    """`None` for non-IP traffic (ARP, etc.) -- it carries no
    connection-level information this feature set uses."""
    if not pkt.haslayer(IP):
        return None

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
