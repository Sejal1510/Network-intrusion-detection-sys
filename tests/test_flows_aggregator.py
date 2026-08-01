import pytest

from nids.data.schema import FEATURE_COLUMNS
from nids.features.contracts import validate_raw_records
from nids.flows.aggregator import FlowAggregator
from nids.flows.schema import PacketEvent


def _pkt(t, src_ip, src_port, dst_ip, dst_port, protocol="tcp", length=60, flags="", frag=False):
    return PacketEvent(
        timestamp=t,
        src_ip=src_ip,
        dst_ip=dst_ip,
        src_port=src_port,
        dst_port=dst_port,
        protocol=protocol,
        length=length,
        tcp_flags=flags,
        fragmented=frag,
    )


def test_normal_sf_connection_end_to_end():
    agg = FlowAggregator()
    packets = [
        _pkt(0.0, "10.0.0.1", 5000, "9.9.9.9", 80, length=60, flags="S"),
        _pkt(0.1, "9.9.9.9", 80, "10.0.0.1", 5000, length=60, flags="SA"),
        _pkt(0.2, "10.0.0.1", 5000, "9.9.9.9", 80, length=40, flags="A"),
        _pkt(0.3, "10.0.0.1", 5000, "9.9.9.9", 80, length=500, flags="PA"),
        _pkt(0.4, "9.9.9.9", 80, "10.0.0.1", 5000, length=1000, flags="PA"),
        _pkt(0.5, "10.0.0.1", 5000, "9.9.9.9", 80, length=40, flags="FA"),
    ]
    record = None
    for pkt in packets:
        result = agg.process_packet(pkt)
        if result is not None:
            record = result

    assert record is not None
    assert record["duration"] == pytest.approx(0.5)
    assert record["protocol_type"] == "tcp"
    assert record["service"] == "http"
    assert record["flag"] == "SF"
    assert record["src_bytes"] == 60 + 40 + 500 + 40
    assert record["dst_bytes"] == 60 + 1000
    assert record["land"] == 0
    assert record["wrong_fragment"] == 0
    assert record["urgent"] == 0
    assert record["count"] == 1
    assert record["srv_count"] == 1
    assert record["serror_rate"] == 0.0
    assert record["rerror_rate"] == 0.0
    assert record["same_srv_rate"] == 1.0
    assert record["diff_srv_rate"] == 0.0
    assert record["dst_host_count"] == 1
    assert record["dst_host_same_src_port_rate"] == 1.0


def test_s0_connection_completes_via_idle_flush():
    agg = FlowAggregator(idle_timeout=2.0)
    agg.process_packet(_pkt(0.0, "10.0.0.1", 5000, "9.9.9.9", 80, flags="S"))

    assert agg.flush_idle(now=1.0) == []  # not yet idle long enough
    records = agg.flush_idle(now=3.0)

    assert len(records) == 1
    record = records[0]
    assert record["flag"] == "S0"
    assert record["serror_rate"] == 1.0
    assert record["rerror_rate"] == 0.0
    assert record["src_bytes"] == 60
    assert record["dst_bytes"] == 0


def test_rej_connection_completes_immediately_on_rst_before_synack():
    agg = FlowAggregator()
    agg.process_packet(_pkt(0.0, "10.0.0.1", 5000, "9.9.9.9", 80, flags="S"))
    result = agg.process_packet(_pkt(0.05, "9.9.9.9", 80, "10.0.0.1", 5000, flags="R"))

    assert result is not None
    assert result["flag"] == "REJ"
    assert result["rerror_rate"] == 1.0
    assert result["serror_rate"] == 0.0


def test_rsto_vs_rstr_distinguished_by_who_sent_the_reset():
    agg = FlowAggregator()
    # full handshake, then originator resets
    agg.process_packet(_pkt(0.0, "10.0.0.1", 5000, "9.9.9.9", 80, flags="S"))
    agg.process_packet(_pkt(0.1, "9.9.9.9", 80, "10.0.0.1", 5000, flags="SA"))
    result = agg.process_packet(_pkt(0.2, "10.0.0.1", 5000, "9.9.9.9", 80, flags="R"))
    assert result["flag"] == "RSTO"

    agg2 = FlowAggregator()
    agg2.process_packet(_pkt(0.0, "10.0.0.2", 5001, "9.9.9.9", 80, flags="S"))
    agg2.process_packet(_pkt(0.1, "9.9.9.9", 80, "10.0.0.2", 5001, flags="SA"))
    result2 = agg2.process_packet(_pkt(0.2, "9.9.9.9", 80, "10.0.0.2", 5001, flags="R"))
    assert result2["flag"] == "RSTR"


def test_count_and_srv_count_accumulate_within_time_window():
    agg = FlowAggregator(time_window=2.0)
    # two rejected connections to the same host:port, then one normal one
    agg.process_packet(_pkt(0.0, "10.0.0.1", 5001, "9.9.9.9", 80, flags="S"))
    agg.process_packet(_pkt(0.1, "9.9.9.9", 80, "10.0.0.1", 5001, flags="R"))

    agg.process_packet(_pkt(0.3, "10.0.0.1", 5002, "9.9.9.9", 80, flags="S"))
    agg.process_packet(_pkt(0.4, "9.9.9.9", 80, "10.0.0.1", 5002, flags="R"))

    agg.process_packet(_pkt(0.6, "10.0.0.1", 5003, "9.9.9.9", 80, flags="S"))
    agg.process_packet(_pkt(0.7, "9.9.9.9", 80, "10.0.0.1", 5003, flags="SA"))
    third = agg.process_packet(_pkt(0.8, "10.0.0.1", 5003, "9.9.9.9", 80, flags="FA"))

    assert third["count"] == 3
    assert third["srv_count"] == 3
    assert third["rerror_rate"] == pytest.approx(2 / 3)
    assert third["serror_rate"] == 0.0
    assert third["same_srv_rate"] == 1.0


def test_time_window_expires_but_dst_host_history_persists():
    agg = FlowAggregator(time_window=2.0)
    agg.process_packet(_pkt(0.0, "10.0.0.1", 5001, "9.9.9.9", 80, flags="S"))
    agg.process_packet(_pkt(0.1, "9.9.9.9", 80, "10.0.0.1", 5001, flags="R"))

    agg.process_packet(_pkt(5.0, "10.0.0.1", 5002, "9.9.9.9", 80, flags="S"))
    second = agg.process_packet(_pkt(5.1, "9.9.9.9", 80, "10.0.0.1", 5002, flags="R"))

    assert second["count"] == 1  # first connection fell out of the 2s window
    assert second["dst_host_count"] == 2  # but not out of the 100-connection host history


def test_unmapped_port_falls_back_to_private_service():
    agg = FlowAggregator()
    agg.process_packet(_pkt(0.0, "10.0.0.1", 5000, "9.9.9.9", 54321, flags="S"))
    record = agg.flush_idle(now=3.0)[0]

    assert record["service"] == "private"


def test_land_attack_pattern_sets_land_flag():
    agg = FlowAggregator()
    agg.process_packet(_pkt(0.0, "10.0.0.1", 80, "10.0.0.1", 80, flags="S"))
    record = agg.flush_idle(now=3.0)[0]

    assert record["land"] == 1


def test_wrong_fragment_and_urgent_are_counted():
    agg = FlowAggregator()
    agg.process_packet(_pkt(0.0, "10.0.0.1", 5000, "9.9.9.9", 80, flags="S", frag=True))
    agg.process_packet(_pkt(0.1, "10.0.0.1", 5000, "9.9.9.9", 80, flags="U", frag=True))
    record = agg.flush_idle(now=3.0)[0]

    assert record["wrong_fragment"] == 2
    assert record["urgent"] == 1


def test_udp_connection_classified_as_sf_when_bidirectional():
    agg = FlowAggregator()
    agg.process_packet(_pkt(0.0, "10.0.0.1", 5000, "9.9.9.9", 53, protocol="udp", length=40))
    agg.process_packet(_pkt(0.1, "9.9.9.9", 53, "10.0.0.1", 5000, protocol="udp", length=80))
    record = agg.flush_idle(now=3.0)[0]

    assert record["protocol_type"] == "udp"
    assert record["flag"] == "SF"


def test_record_satisfies_the_shared_raw_record_contract():
    """The whole point: a flow record must pass the exact same
    validation every other input path (batch CSV, live agent) goes
    through -- nids.features.contracts.validate_raw_records."""
    import pandas as pd

    agg = FlowAggregator()
    agg.process_packet(_pkt(0.0, "10.0.0.1", 5000, "9.9.9.9", 80, flags="S"))
    record = agg.flush_idle(now=3.0)[0]

    assert set(record.keys()) == set(FEATURE_COLUMNS)
    validate_raw_records(pd.DataFrame([record]))  # must not raise
