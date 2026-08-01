"""The live capture agent: runs on a user's own machine, captures local
traffic (or replays a saved `.pcap`/dataset), and streams flow records to
`nids.api.ingest` over an outbound WebSocket connection. Never runs
prediction/explanation/risk/alert logic itself -- that's the server's job
(`nids.api.pipeline`), reused unchanged; the agent's only job is producing
raw records satisfying `nids.data.schema.FEATURE_COLUMNS`.
"""
