"""Structured logging setup -- the first logging *configuration* in this
codebase (previously: none; every module's own `logging.getLogger(__name__)`
call -- `nids.api.worker`, `nids.agent.client`, `nids.agent.capture` -- has
always relied on Python's unconfigured root logger). Applied once, at
process startup, from `nids.api.cli.main`, before `create_app` builds
anything -- every existing `getLogger(__name__)` call picks this up
automatically via normal logger propagation, with zero changes to those
modules.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class JsonFormatter(logging.Formatter):
    """One JSON object per line -- the shape a log aggregator (e.g. in a
    docker-compose/Kubernetes deployment) expects, vs. the plain-text
    default meant for a human staring at a terminal."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging(level: str = "INFO", json_format: bool = False) -> None:
    """Configure the root logger once, at process startup. `json_format`
    is opt-in (default `False`, human-readable text) since it only earns
    its keep once something downstream actually parses the output (a log
    aggregator) -- a local `docker compose up` or bare `python -m
    nids.api` run has no such consumer."""
    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter()
        if json_format
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """One line per request: method, path, status, duration_ms, client IP
    -- the same client-IP concept `nids.api.rate_limit` keys its counters
    on and `nids.api.store`'s audit trail records as `actor`."""

    def __init__(self, app: Any, logger: logging.Logger | None = None) -> None:
        super().__init__(app)
        self._logger = logger or logging.getLogger("nids.api.request")

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        client_host = request.client.host if request.client else "unknown"
        self._logger.info(
            "%s %s -> %s (%.1fms) client=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            client_host,
        )
        return response
