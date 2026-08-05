"""Prometheus metrics: process-wide counters/histograms exposed at
GET /metrics in Prometheus text exposition format (`prometheus_client`,
new dependency -- see docs/OBSERVABILITY.md).

Deliberately the only module that imports `prometheus_client`, mirroring
how `nids.api.bus`/`nids.api.store` are the sole importers of `redis`/
`sqlalchemy`.

`create_metrics()` builds a fresh `CollectorRegistry` per call rather than
registering against `prometheus_client`'s process-wide default registry --
the same "no module-level singleton, explicit instance per `create_app()`"
convention `nids.api.bus.create_bus`/`nids.api.store.create_db_engine`
already use for everything else on `app.state`. Besides consistency, it's
required here: the default global registry raises on a second
registration of the same metric name, which every second `create_app()`
call in the same process (i.e. every test module) would trigger.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


@dataclass(frozen=True)
class Metrics:
    registry: CollectorRegistry
    http_requests_total: Counter
    http_request_duration_seconds: Histogram
    prediction_duration_seconds: Histogram
    alerts_raised_total: Counter


def create_metrics() -> Metrics:
    registry = CollectorRegistry()
    return Metrics(
        registry=registry,
        http_requests_total=Counter(
            "nids_http_requests_total",
            "Total HTTP requests.",
            ["method", "route", "status"],
            registry=registry,
        ),
        http_request_duration_seconds=Histogram(
            "nids_http_request_duration_seconds",
            "HTTP request duration in seconds.",
            ["method", "route", "status"],
            registry=registry,
        ),
        prediction_duration_seconds=Histogram(
            "nids_prediction_duration_seconds",
            "Time spent producing a prediction response. For route=/predict/batch "
            "this wraps only the nids.api.inference.predict_batch call; for "
            "route=/predict it wraps the whole per-record pipeline "
            "(nids.api.pipeline.process_record), since /predict has no "
            "inference-only call site in app.py to isolate -- the two labels "
            "are not apples-to-apples (see docs/OBSERVABILITY.md).",
            ["route"],
            registry=registry,
        ),
        alerts_raised_total=Counter(
            "nids_alerts_raised_total",
            "Total alerts raised (RiskScore crossing alert_threshold).",
            ["source"],
            registry=registry,
        ),
    )


def metrics_response(metrics: Metrics) -> Response:
    return Response(generate_latest(metrics.registry), media_type=CONTENT_TYPE_LATEST)


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Records `http_requests_total`/`http_request_duration_seconds` for
    every request, labeled by the *route template* (e.g.
    `/history/predictions/{prediction_id}`), not the raw resolved path --
    keeps cardinality bounded regardless of how many distinct ids get
    requested."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        route = request.scope.get("route")
        route_path = route.path if route is not None else request.url.path
        metrics: Metrics = request.app.state.metrics
        labels = {"method": request.method, "route": route_path, "status": str(response.status_code)}
        metrics.http_requests_total.labels(**labels).inc()
        metrics.http_request_duration_seconds.labels(**labels).observe(duration)
        return response
