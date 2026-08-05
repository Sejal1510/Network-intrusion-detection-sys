"""Live worker: consumes the `MessageBus` `"flows"` channel (populated by
`nids.api.ingest`) and runs each flow record through
`nids.api.pipeline.process_record` -- the *same* orchestration the HTTP
`/predict` route uses, just triggered by a bus message instead of an HTTP
request. Publishes the resulting response (as a JSON-safe dict) to the
`"live"` channel for `nids.api.broadcast` to fan out to dashboard clients.

Explains only alert-worthy flows by default: running SHAP for every live
flow would make explainability a throughput bottleneck for the (large)
majority of normal traffic that never becomes an alert -- see
`nids.api.pipeline.ExplainPolicy`.

Runs forever. For the `InMemoryBus` tier, `create_app` starts this as a
background `asyncio` task in the same process. For the `RedisBus` tier,
it's meant to run as its own process (`python -m nids.api.worker`),
scaling independently of the API/ingestion process via Redis Streams
consumer groups.
"""

from __future__ import annotations

import logging

from sqlalchemy.engine import Engine

from nids.api.bus import MessageBus
from nids.api.config import ServingConfig
from nids.api.inference import PredictionResult
from nids.api.metrics import Metrics
from nids.api.model_loader import ServedEnsemble
from nids.api.pipeline import process_record
from nids.api.risk import RiskScore

logger = logging.getLogger(__name__)


def explain_only_alert_worthy(
    result: PredictionResult, risk_score: RiskScore, *, threshold: float
) -> bool:
    """The live worker's explain policy: SHAP only for flows that will
    actually raise an alert (the ones a human will look at), never for
    the majority of normal traffic."""
    return risk_score.score >= threshold


async def process_flow_message(
    message: dict,
    bus: MessageBus,
    served_ensemble: ServedEnsemble,
    config: ServingConfig,
    db_engine: Engine | None,
    metrics: Metrics,
) -> None:
    """Process one `"flows"`-channel message: run the pipeline, publish
    the result. A single record's failure (an invalid flow, or any other
    unexpected error) is logged and dropped -- it must never take down
    the worker loop, which would stop monitoring for every device, not
    just the one that sent the bad message."""
    device_id = message.get("device_id")
    record = message.get("record")

    try:
        response = process_record(
            served_ensemble,
            record,
            config=config,
            db_engine=db_engine,
            explain=lambda result, risk_score: explain_only_alert_worthy(
                result, risk_score, threshold=config.alert_threshold
            ),
            source="agent",
            device_id=device_id,
        )
    except ValueError as exc:
        logger.warning("Dropping invalid flow record from device %s: %s", device_id, exc)
        return
    except Exception:
        logger.exception("Unexpected error processing flow record from device %s", device_id)
        return

    if response.alert_id is not None:
        metrics.alerts_raised_total.labels(source="agent").inc()
    await bus.publish("live", response.model_dump(mode="json"))


async def run_worker(
    bus: MessageBus,
    served_ensemble: ServedEnsemble,
    config: ServingConfig,
    db_engine: Engine | None,
    metrics: Metrics,
) -> None:
    """Runs forever, consuming the `"flows"` channel one message at a
    time."""
    async for message in bus.subscribe("flows"):
        await process_flow_message(message, bus, served_ensemble, config, db_engine, metrics)
