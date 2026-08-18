from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nids.api.app import create_app
from nids.api.config import ServingConfig
from nids.data import loader
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
        run_name="security-headers-fixture-run",
    )
    run_training(config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)

    serving_config = ServingConfig(
        run_id="security-headers-fixture-run", artifact_root=tmp_path / "runs"
    )
    return TestClient(create_app(serving_config))


def test_health_response_carries_security_headers(client):
    response = client.get("/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert "camera=()" in response.headers["Permissions-Policy"]


def test_404_response_still_carries_security_headers(client):
    """Error responses need these headers too -- a browser rendering an
    unexpected error body shouldn't fall back to unsafe defaults just
    because the route didn't match."""
    response = client.get("/this-route-does-not-exist")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
