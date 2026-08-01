"""Packets -> raw records: the layer `docs/FEATURE_PIPELINE.md` has
reserved since Milestone 1 for "PCAP-derived flow records" and "Live
capture agent". Sits between packet capture (`nids.agent`, or a `.pcap`
file) and `nids.features` -- its only job is producing dicts that satisfy
`nids.data.schema.FEATURE_COLUMNS`, the exact contract batch CSV upload
already satisfies. Nothing here knows about models, HTTP, or WebSockets.
"""

from nids.flows.aggregator import FlowAggregator
from nids.flows.schema import PacketEvent

__all__ = ["FlowAggregator", "PacketEvent"]
