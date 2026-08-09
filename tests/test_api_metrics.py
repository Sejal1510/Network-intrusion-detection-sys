import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nids.api.app import create_app
from nids.api.config import ServingConfig
from nids.data import loader
from nids.data.schema import FEATURE_COLUMNS
from nids.training.config import TrainingConfig
from nids.training.run import run_training

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd.txt"


@pytest.fixture
def fixture_df():
    return loader._read_nsl_kdd_file(FIXTURE)


@pytest.fixture
def client(fixture_df, tmp_path):
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        artifact_root=tmp_path / "runs",
        run_name="metrics-fixture-run",
    )
    run_training(config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)

    serving_config = ServingConfig(run_id="metrics-fixture-run", artifact_root=tmp_path / "runs")
    app = create_app(serving_config)
    return TestClient(app)


@pytest.fixture
def valid_record(fixture_df) -> dict:
    record = fixture_df.iloc[0].to_dict()
    return {k: record[k] for k in FEATURE_COLUMNS}


def test_metrics_endpoint_returns_prometheus_text_exposition_format(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "nids_http_requests_total" in response.text


def test_http_request_metrics_increment_after_a_request(client):
    client.get("/health")
    body = client.get("/metrics").text
    assert 'nids_http_requests_total{method="GET",route="/health",status="200"}' in body


def test_prediction_duration_metric_recorded_after_predict(client, valid_record):
    client.post("/predict", json=valid_record)
    body = client.get("/metrics").text
    assert 'nids_prediction_duration_seconds_count{route="/predict"} 1.0' in body


def test_prediction_duration_metric_recorded_after_predict_batch(client, fixture_df):
    csv_bytes = fixture_df[FEATURE_COLUMNS].to_csv(index=False).encode()
    client.post("/predict/batch", files={"file": ("records.csv", io.BytesIO(csv_bytes), "text/csv")})
    body = client.get("/metrics").text
    assert 'nids_prediction_duration_seconds_count{route="/predict/batch"} 1.0' in body


def test_metrics_are_isolated_per_app_instance(fixture_df, tmp_path):
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        artifact_root=tmp_path / "runs",
        run_name="metrics-fixture-run",
    )
    run_training(config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)
    serving_config = ServingConfig(run_id="metrics-fixture-run", artifact_root=tmp_path / "runs")

    client_a = TestClient(create_app(serving_config))
    client_b = TestClient(create_app(serving_config))

    record = {k: fixture_df.iloc[0].to_dict()[k] for k in FEATURE_COLUMNS}
    client_a.post("/predict", json=record)

    body_a = client_a.get("/metrics").text
    body_b = client_b.get("/metrics").text
    assert 'nids_prediction_duration_seconds_count{route="/predict"} 1.0' in body_a
    assert 'nids_prediction_duration_seconds_count{route="/predict"}' not in body_b


# --- metrics_summary (unit-level, no HTTP) ----------------------------------


def test_metrics_summary_starts_empty():
    from nids.api.metrics import create_metrics, metrics_summary

    summary = metrics_summary(create_metrics())

    assert summary.http_requests_total == 0.0
    assert summary.alerts_by_source == {}
    assert summary.notifications_by_channel == {}
    assert summary.predictions_by_route == {}
    assert summary.avg_prediction_duration_seconds == {}


def test_metrics_summary_aggregates_alerts_by_source():
    from nids.api.metrics import create_metrics, metrics_summary

    metrics = create_metrics()
    metrics.alerts_raised_total.labels(source="api").inc(3)
    metrics.alerts_raised_total.labels(source="rule").inc(2)
    metrics.alerts_raised_total.labels(source="agent").inc(1)

    summary = metrics_summary(metrics)

    assert summary.alerts_by_source == {"api": 3.0, "rule": 2.0, "agent": 1.0}


def test_metrics_summary_nests_notifications_by_channel_and_status():
    from nids.api.metrics import create_metrics, metrics_summary

    metrics = create_metrics()
    metrics.notifications_sent_total.labels(
        channel="SlackNotificationChannel", status="success"
    ).inc(5)
    metrics.notifications_sent_total.labels(
        channel="SlackNotificationChannel", status="failure"
    ).inc(1)
    metrics.notifications_sent_total.labels(
        channel="EmailNotificationChannel", status="success"
    ).inc(2)

    summary = metrics_summary(metrics)

    assert summary.notifications_by_channel == {
        "SlackNotificationChannel": {"success": 5.0, "failure": 1.0},
        "EmailNotificationChannel": {"success": 2.0},
    }


def test_metrics_summary_computes_average_prediction_duration():
    from nids.api.metrics import create_metrics, metrics_summary

    metrics = create_metrics()
    metrics.prediction_duration_seconds.labels(route="/predict").observe(0.1)
    metrics.prediction_duration_seconds.labels(route="/predict").observe(0.3)
    metrics.prediction_duration_seconds.labels(route="/predict/batch").observe(0.5)

    summary = metrics_summary(metrics)

    assert summary.predictions_by_route == {"/predict": 2.0, "/predict/batch": 1.0}
    assert summary.avg_prediction_duration_seconds["/predict"] == pytest.approx(0.2)
    assert summary.avg_prediction_duration_seconds["/predict/batch"] == pytest.approx(0.5)


def test_metrics_summary_counts_http_requests_across_all_labels():
    from nids.api.metrics import create_metrics, metrics_summary

    metrics = create_metrics()
    metrics.http_requests_total.labels(method="GET", route="/health", status="200").inc(4)
    metrics.http_requests_total.labels(method="POST", route="/predict", status="200").inc(6)

    summary = metrics_summary(metrics)

    assert summary.http_requests_total == 10.0
