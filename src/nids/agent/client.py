"""Agent WebSocket client: exchanges a pairing token for a device
credential, then connects outbound to the server's `/agent/ingest`
endpoint and sends flow records from a `FlowSource`. Reconnects with
exponential backoff + jitter on any disconnect -- retried indefinitely,
since the agent is meant to run unattended.

Buffers records in a bounded ring buffer while disconnected or
send-constrained; overflow policy is drop-oldest -- live monitoring
favors recency and availability over perfect historical completeness (a
deliberate trade-off, not an oversight -- see `docs/LIVE_MONITORING.md`).

Uses `requests` (already a project dependency) for the one-off pairing
HTTP calls and `websockets` for the persistent connection -- no new HTTP
client library for what's a handful of REST calls.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from collections import deque
from typing import Any

import requests
import websockets
import websockets.exceptions

from nids.agent.sources import FlowSource

logger = logging.getLogger(__name__)

DEFAULT_BUFFER_SIZE = 1000
DEFAULT_MAX_BACKOFF_SECONDS = 60.0


def request_pairing_token(base_url: str) -> str:
    """`POST /agent/pair` -- the first half of pairing a new device (see
    `nids.api.agent_auth`). Returns the short-lived pairing code a human
    enters into `python -m nids.agent pair <code>`."""
    response = requests.post(f"{base_url}/agent/pair", timeout=10)
    response.raise_for_status()
    return response.json()["pairing_token"]


def exchange_pairing_token(base_url: str, pairing_token: str, device_name: str) -> str:
    """`POST /agent/pair/exchange` -- redeems a pairing code for a
    long-lived device credential (bearer token) used for every
    subsequent `/agent/ingest` connection."""
    response = requests.post(
        f"{base_url}/agent/pair/exchange",
        json={"pairing_token": pairing_token, "device_name": device_name},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["token"]


class AgentClient:
    """Owns the outbound WebSocket connection: a `FlowSource` feeds
    records into a bounded buffer (`_produce`); a separate loop drains
    the buffer to the server, reconnecting with backoff on any failure
    (`_send_loop`). The two run concurrently via `run()` so capture never
    blocks on network I/O.
    """

    def __init__(
        self,
        ws_url: str,
        device_token: str,
        source: FlowSource,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
        max_backoff_seconds: float = DEFAULT_MAX_BACKOFF_SECONDS,
    ) -> None:
        self._ws_url = ws_url
        self._device_token = device_token
        self._source = source
        self._buffer: deque[dict[str, Any]] = deque(maxlen=buffer_size)
        self._max_backoff_seconds = max_backoff_seconds
        self._buffer_not_empty = asyncio.Event()

    async def _produce(self) -> None:
        async for record in self._source.records():
            if len(self._buffer) == self._buffer.maxlen:
                logger.warning(
                    "Buffer full (%d records) -- dropping oldest record.", self._buffer.maxlen
                )
            self._buffer.append(record)
            self._buffer_not_empty.set()

    async def _drain(self, ws: Any) -> None:
        while True:
            if not self._buffer:
                self._buffer_not_empty.clear()
                await self._buffer_not_empty.wait()
                continue
            record = self._buffer.popleft()
            try:
                await ws.send(json.dumps(record))
            except (websockets.exceptions.WebSocketException, OSError):
                self._buffer.appendleft(record)  # put it back; the outer loop will reconnect
                raise

    async def _send_loop(self) -> None:
        attempt = 0
        while True:
            try:
                async with websockets.connect(
                    self._ws_url,
                    additional_headers={"Authorization": f"Bearer {self._device_token}"},
                ) as ws:
                    logger.info("Connected to %s", self._ws_url)
                    attempt = 0
                    await self._drain(ws)
            except (websockets.exceptions.WebSocketException, OSError) as exc:
                delay = min(self._max_backoff_seconds, 2**attempt) + random.uniform(0, 1)
                logger.warning("Connection to %s failed (%s); retrying in %.1fs", self._ws_url, exc, delay)
                await asyncio.sleep(delay)
                attempt += 1

    async def run(self) -> None:
        """Runs forever: captures/replays flow records and streams them
        to the server, reconnecting indefinitely on any disconnect."""
        await asyncio.gather(self._produce(), self._send_loop())
