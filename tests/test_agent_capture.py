import asyncio

from scapy.layers.inet import IP, TCP
from scapy.layers.l2 import ARP, Ether

from nids.agent.capture import LiveCapture


async def test_on_packet_enqueues_event_when_loop_is_set():
    capture = LiveCapture()
    capture._loop = asyncio.get_running_loop()
    pkt = IP(src="10.0.0.1", dst="9.9.9.9") / TCP(sport=5000, dport=80, flags="S")

    capture._on_packet(pkt)

    event = await asyncio.wait_for(capture.events().__anext__(), timeout=1)
    assert event.src_ip == "10.0.0.1"
    assert event.dst_port == 80


def test_on_packet_does_nothing_without_a_running_loop():
    capture = LiveCapture()  # start() never called -- no loop set
    pkt = IP(src="10.0.0.1", dst="9.9.9.9") / TCP(sport=5000, dport=80, flags="S")

    capture._on_packet(pkt)  # must not raise

    assert capture._queue.empty()


async def test_on_packet_ignores_non_ip_packets():
    capture = LiveCapture()
    capture._loop = asyncio.get_running_loop()

    capture._on_packet(Ether() / ARP())

    assert capture._queue.empty()
