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
        run_name="app-fixture-run",
    )
    run_training(config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)

    serving_config = ServingConfig(run_id="app-fixture-run", artifact_root=tmp_path / "runs")
    app = create_app(serving_config)
    return TestClient(app)


@pytest.fixture
def valid_record(fixture_df) -> dict:
    record = fixture_df.iloc[0].to_dict()
    return {k: record[k] for k in FEATURE_COLUMNS}


def test_health_reports_model_loaded(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True


def test_model_info_returns_served_run_metadata_and_metrics(client):
    response = client.get("/model")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "app-fixture-run"
    assert body["model_name"] == "random_forest"
    assert "accuracy" in body["metrics"]


def test_predict_returns_prediction_for_a_valid_record(client, valid_record):
    response = client.post("/predict", json=valid_record)

    assert response.status_code == 200
    body = response.json()
    assert body["prediction"] in (0, 1)
    assert body["probabilities"] is not None


def test_predict_rejects_request_missing_a_required_field(client, valid_record):
    del valid_record["duration"]

    response = client.post("/predict", json=valid_record)

    assert response.status_code == 422


def test_predict_rejects_unknown_extra_field(client, valid_record):
    valid_record["not_a_real_field"] = 1

    response = client.post("/predict", json=valid_record)

    assert response.status_code == 422


def test_predict_batch_returns_summary_and_per_row_results(client, fixture_df):
    csv_bytes = fixture_df.to_csv(index=False).encode("utf-8")

    response = client.post(
        "/predict/batch", files={"file": ("sample.csv", io.BytesIO(csv_bytes), "text/csv")}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["total_records"] == len(fixture_df)
    assert len(body["results"]) == len(fixture_df)
    assert sum(body["summary"]["prediction_counts"].values()) == len(fixture_df)


def test_predict_batch_rejects_csv_missing_required_columns(client, fixture_df):
    incomplete_df = fixture_df.drop(columns=["duration"])
    csv_bytes = incomplete_df.to_csv(index=False).encode("utf-8")

    response = client.post(
        "/predict/batch", files={"file": ("sample.csv", io.BytesIO(csv_bytes), "text/csv")}
    )

    assert response.status_code == 400
    assert "duration" in response.json()["detail"]


def test_predict_batch_rejects_non_csv_file(client):
    response = client.post(
        "/predict/batch", files={"file": ("sample.txt", io.BytesIO(b"not a csv"), "text/plain")}
    )

    assert response.status_code == 400
