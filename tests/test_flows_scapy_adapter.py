from scapy.layers.inet import IP, TCP, UDP

from nids.flows.scapy_adapter import to_packet_event


def test_to_packet_event_extracts_tcp_fields():
    pkt = IP(src="10.0.0.1", dst="9.9.9.9") / TCP(sport=5000, dport=80, flags="S")
    pkt.time = 1700000000.0

    event = to_packet_event(pkt)

    assert event is not None
    assert event.src_ip == "10.0.0.1"
    assert event.dst_ip == "9.9.9.9"
    assert event.src_port == 5000
    assert event.dst_port == 80
    assert event.protocol == "tcp"
    assert event.tcp_flags == "S"
    assert event.timestamp == 1700000000.0


def test_to_packet_event_extracts_udp_fields():
    pkt = IP(src="10.0.0.1", dst="9.9.9.9") / UDP(sport=6000, dport=53)

    event = to_packet_event(pkt)

    assert event.protocol == "udp"
    assert event.tcp_flags == ""


def test_to_packet_event_returns_none_for_non_ip_packet():
    from scapy.layers.l2 import ARP, Ether

    pkt = Ether() / ARP()

    assert to_packet_event(pkt) is None


def test_to_packet_event_detects_fragmentation():
    fragmented = IP(src="10.0.0.1", dst="9.9.9.9", frag=5) / UDP(sport=1, dport=2)
    not_fragmented = IP(src="10.0.0.1", dst="9.9.9.9") / UDP(sport=1, dport=2)

    assert to_packet_event(fragmented).fragmented is True
    assert to_packet_event(not_fragmented).fragmented is False
