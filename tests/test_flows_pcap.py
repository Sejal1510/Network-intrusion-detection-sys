from pathlib import Path

from nids.flows.aggregator import FlowAggregator
from nids.flows.pcap import iter_packet_events_from_pcap

FIXTURE = Path(__file__).parent / "fixtures" / "sample_capture.pcap"


def test_iter_packet_events_reads_every_ip_packet_in_order():
    events = list(iter_packet_events_from_pcap(FIXTURE))

    assert len(events) == 5
    assert [e.protocol for e in events] == ["tcp", "tcp", "tcp", "tcp", "udp"]
    assert events == sorted(events, key=lambda e: e.timestamp)  # capture order preserved


def test_tcp_packet_fields_extracted_correctly():
    events = list(iter_packet_events_from_pcap(FIXTURE))
    syn = events[0]

    assert syn.src_ip == "10.0.0.1"
    assert syn.dst_ip == "9.9.9.9"
    assert syn.src_port == 5000
    assert syn.dst_port == 80
    assert syn.tcp_flags == "S"
    assert syn.fragmented is False


def test_udp_packet_has_no_tcp_flags():
    events = list(iter_packet_events_from_pcap(FIXTURE))
    udp_event = events[-1]

    assert udp_event.protocol == "udp"
    assert udp_event.tcp_flags == ""
    assert udp_event.src_port == 6000
    assert udp_event.dst_port == 53


def test_pcap_events_feed_the_same_flow_aggregator_as_live_capture():
    """The whole point of sharing PacketEvent: a file-derived stream and
    a live-derived stream are indistinguishable to FlowAggregator."""
    agg = FlowAggregator()
    record = None
    for event in iter_packet_events_from_pcap(FIXTURE):
        result = agg.process_packet(event)
        if result is not None and event.protocol == "tcp":
            record = result

    assert record is not None
    assert record["flag"] == "SF"
    assert record["protocol_type"] == "tcp"
    assert record["service"] == "http"
