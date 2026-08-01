import asyncio
from pathlib import Path

import pytest

from nids.api.bus import InMemoryBus
from nids.api.config import ServingConfig
from nids.api.model_loader import ServedEnsemble, ServedModel
from nids.api.worker import explain_only_alert_worthy, process_flow_message, run_worker
from nids.data import loader
from nids.data.schema import FEATURE_COLUMNS
from nids.training.config import TrainingConfig
from nids.training.core import fit_and_evaluate

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd.txt"


@pytest.fixture
def fixture_df():
    return loader._read_nsl_kdd_file(FIXTURE)


@pytest.fixture
def served_ensemble(fixture_df):
    config = TrainingConfig(model_name="random_forest", model_params={"n_estimators": 5})
    result = fit_and_evaluate(fixture_df, fixture_df, config)
    classifier = ServedModel(
        run_id="test-run",
        model=result.model,
        feature_engineer=result.feature_engineer,
        metrics=result.metrics,
        metadata={"model_name": "random_forest", "label_column": "is_attack"},
    )
    return ServedEnsemble(classifier=classifier, anomaly_detector=None)


@pytest.fixture
def valid_record(fixture_df) -> dict:
    row = fixture_df.iloc[0].to_dict()
    return {k: row[k] for k in FEATURE_COLUMNS}


def test_explain_only_alert_worthy_true_at_or_above_threshold():
    from nids.api.risk import RiskScore

    risk = RiskScore(score=80.0, severity="high", factors={})
    assert explain_only_alert_worthy(None, risk, threshold=70.0) is True


def test_explain_only_alert_worthy_false_below_threshold():
    from nids.api.risk import RiskScore

    risk = RiskScore(score=10.0, severity="low", factors={})
    assert explain_only_alert_worthy(None, risk, threshold=70.0) is False


async def test_process_flow_message_publishes_result_to_live_channel(served_ensemble, valid_record):
    bus = InMemoryBus()
    config = ServingConfig(run_id="test-run", alert_threshold=0.0)

    async def consume_one():
        async for message in bus.subscribe("live"):
            return message

    task = asyncio.create_task(consume_one())
    await asyncio.sleep(0)

    await process_flow_message(
        {"device_id": "device-1", "record": valid_record}, bus, served_ensemble, config, None
    )

    result = await asyncio.wait_for(task, timeout=1)
    assert "prediction" in result
    assert "risk_score" in result


async def test_process_flow_message_explains_only_when_alert_worthy(served_ensemble, valid_record):
    bus = InMemoryBus()
    low_threshold_config = ServingConfig(run_id="test-run", alert_threshold=0.0)

    async def consume_one():
        async for message in bus.subscribe("live"):
            return message

    task = asyncio.create_task(consume_one())
    await asyncio.sleep(0)

    await process_flow_message(
        {"device_id": "device-1", "record": valid_record}, bus, served_ensemble, low_threshold_config, None
    )

    result = await asyncio.wait_for(task, timeout=1)
    assert result["alert_id"] is not None
    assert result["explanation"] is not None  # alert-worthy -- explained


async def test_process_flow_message_skips_explanation_when_not_alert_worthy(served_ensemble, valid_record):
    bus = InMemoryBus()
    high_threshold_config = ServingConfig(run_id="test-run", alert_threshold=1000.0)

    async def consume_one():
        async for message in bus.subscribe("live"):
            return message

    task = asyncio.create_task(consume_one())
    await asyncio.sleep(0)

    await process_flow_message(
        {"device_id": "device-1", "record": valid_record}, bus, served_ensemble, high_threshold_config, None
    )

    result = await asyncio.wait_for(task, timeout=1)
    assert result["alert_id"] is None
    assert result["explanation"] is None


async def test_process_flow_message_drops_invalid_record_without_publishing(served_ensemble):
    bus = InMemoryBus()
    config = ServingConfig(run_id="test-run")

    published = []

    async def consume_one():
        async for message in bus.subscribe("live"):
            published.append(message)
            return

    task = asyncio.create_task(consume_one())
    await asyncio.sleep(0)

    await process_flow_message(
        {"device_id": "device-1", "record": {"duration": 0}}, bus, served_ensemble, config, None
    )

    # nothing should be published for an invalid record; confirm by
    # publishing a sentinel afterward and observing only the sentinel
    await bus.publish("live", {"sentinel": True})
    await asyncio.wait_for(task, timeout=1)
    assert published == [{"sentinel": True}]


async def test_run_worker_processes_multiple_messages(served_ensemble, valid_record):
    bus = InMemoryBus()
    config = ServingConfig(run_id="test-run", alert_threshold=1000.0)

    received = []

    async def consume():
        async for message in bus.subscribe("live"):
            received.append(message)
            if len(received) == 2:
                return

    worker_task = asyncio.create_task(run_worker(bus, served_ensemble, config, None))
    consumer_task = asyncio.create_task(consume())
    await asyncio.sleep(0)

    await bus.publish("flows", {"device_id": "device-1", "record": valid_record})
    await bus.publish("flows", {"device_id": "device-2", "record": valid_record})

    await asyncio.wait_for(consumer_task, timeout=2)
    worker_task.cancel()

    assert len(received) == 2
