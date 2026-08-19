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
    notifications_sent_total: Counter
    ioc_enrichment_lookups_total: Counter


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
        notifications_sent_total=Counter(
            "nids_notifications_sent_total",
            "Total notification channel send attempts (nids.api.notifications), "
            "labeled by channel class name and outcome.",
            ["channel", "status"],
            registry=registry,
        ),
        ioc_enrichment_lookups_total=Counter(
            "nids_ioc_enrichment_lookups_total",
            "Total threat-intel provider lookup attempts (nids.api.threat_intel), "
            "labeled by provider name and outcome. Cache hits (no external call "
            "made) are not counted here -- this measures external usage.",
            ["provider", "status"],
            registry=registry,
        ),
    )


def metrics_response(metrics: Metrics) -> Response:
    return Response(generate_latest(metrics.registry), media_type=CONTENT_TYPE_LATEST)


@dataclass(frozen=True)
class MetricsSummary:
    """A small, JSON-friendly read of the same counters `/metrics`
    already exposes in Prometheus text format -- for the dashboard's
    Metrics page (`nids.api.app`'s `GET /metrics/summary`), which has no
    Prometheus/Grafana stack to query. Not a replacement for `/metrics`:
    that stays the real scrape target; this is a convenience view over
    the handful of counters worth a human glancing at directly."""

    http_requests_total: float
    alerts_by_source: dict[str, float]
    notifications_by_channel: dict[str, dict[str, float]]
    predictions_by_route: dict[str, float]
    avg_prediction_duration_seconds: dict[str, float]


def metrics_summary(metrics: Metrics) -> MetricsSummary:
    """Walks `metrics.registry`'s current sample values -- the same data
    `generate_latest` serializes to Prometheus text -- and reshapes the
    handful of counters worth a human glancing at into plain JSON.
    `_created` timestamp samples (`prometheus_client` emits one per
    series) and histogram bucket samples are skipped; only `_total`/
    `_count`/`_sum` samples are read."""
    http_requests_total = 0.0
    alerts_by_source: dict[str, float] = {}
    notifications_by_channel: dict[str, dict[str, float]] = {}
    prediction_count: dict[str, float] = {}
    prediction_sum: dict[str, float] = {}

    for family in metrics.registry.collect():
        for sample in family.samples:
            if sample.name == "nids_http_requests_total":
                http_requests_total += sample.value
            elif sample.name == "nids_alerts_raised_total":
                source = sample.labels.get("source", "unknown")
                alerts_by_source[source] = alerts_by_source.get(source, 0.0) + sample.value
            elif sample.name == "nids_notifications_sent_total":
                channel = sample.labels.get("channel", "unknown")
                status = sample.labels.get("status", "unknown")
                notifications_by_channel.setdefault(channel, {})
                notifications_by_channel[channel][status] = (
                    notifications_by_channel[channel].get(status, 0.0) + sample.value
                )
            elif sample.name == "nids_prediction_duration_seconds_count":
                route = sample.labels.get("route", "unknown")
                prediction_count[route] = prediction_count.get(route, 0.0) + sample.value
            elif sample.name == "nids_prediction_duration_seconds_sum":
                route = sample.labels.get("route", "unknown")
                prediction_sum[route] = prediction_sum.get(route, 0.0) + sample.value

    avg_prediction_duration_seconds = {
        route: (prediction_sum[route] / count if count > 0 else 0.0)
        for route, count in prediction_count.items()
    }

    return MetricsSummary(
        http_requests_total=http_requests_total,
        alerts_by_source=alerts_by_source,
        notifications_by_channel=notifications_by_channel,
        predictions_by_route=prediction_count,
        avg_prediction_duration_seconds=avg_prediction_duration_seconds,
    )


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
