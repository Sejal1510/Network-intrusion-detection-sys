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
def hybrid_client(fixture_df, tmp_path):
    classifier_config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        artifact_root=tmp_path / "runs",
        run_name="app-fixture-run",
    )
    run_training(classifier_config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)

    anomaly_config = TrainingConfig(
        model_name="isolation_forest",
        artifact_root=tmp_path / "runs",
        run_name="anomaly-fixture-run",
    )
    run_training(anomaly_config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)

    serving_config = ServingConfig(
        run_id="app-fixture-run",
        anomaly_run_id="anomaly-fixture-run",
        artifact_root=tmp_path / "runs",
    )
    app = create_app(serving_config)
    return TestClient(app)


@pytest.fixture
def persisted_client(fixture_df, tmp_path):
    """A client with database_url configured -- exercises the opt-in
    persistence path end-to-end."""
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        artifact_root=tmp_path / "runs",
        run_name="app-fixture-run",
    )
    run_training(config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)

    serving_config = ServingConfig(
        run_id="app-fixture-run",
        artifact_root=tmp_path / "runs",
        database_url=f"sqlite:///{tmp_path / 'history.db'}",
    )
    app = create_app(serving_config)
    return TestClient(app), app


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
    assert body["severity"] in {"critical", "high", "medium", "low"}


def test_predict_classifier_only_leaves_anomaly_fields_null(client, valid_record):
    """Milestone 2 regression: no --anomaly-run-id means no anomaly fields."""
    response = client.post("/predict", json=valid_record)

    body = response.json()
    assert body["anomaly_score"] is None
    assert body["is_anomaly"] is None


def test_model_info_anomaly_detector_is_null_when_not_served(client):
    response = client.get("/model")

    assert response.json()["anomaly_detector"] is None


def test_predict_with_hybrid_serving_populates_anomaly_fields(hybrid_client, valid_record):
    response = hybrid_client.post("/predict", json=valid_record)

    assert response.status_code == 200
    body = response.json()
    assert body["anomaly_score"] is not None
    assert 0.0 <= body["anomaly_score"] <= 1.0
    assert isinstance(body["is_anomaly"], bool)
    assert body["severity"] in {"critical", "high", "medium", "low"}


def test_model_info_reports_anomaly_detector_when_served(hybrid_client):
    response = hybrid_client.get("/model")

    body = response.json()
    assert body["anomaly_detector"]["run_id"] == "anomaly-fixture-run"
    assert body["anomaly_detector"]["model_name"] == "isolation_forest"


def test_predict_batch_with_hybrid_serving_populates_anomaly_fields(hybrid_client, fixture_df):
    csv_bytes = fixture_df.to_csv(index=False).encode("utf-8")

    response = hybrid_client.post(
        "/predict/batch", files={"file": ("sample.csv", io.BytesIO(csv_bytes), "text/csv")}
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == len(fixture_df)
    assert all(r["anomaly_score"] is not None for r in results)


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


def test_predict_without_explain_param_leaves_explanation_null(client, valid_record):
    """Milestone 3 regression: default behavior is unaffected by the new
    explainability layer."""
    response = client.post("/predict", json=valid_record)

    assert response.json()["explanation"] is None


def test_predict_with_explain_true_populates_explanation(client, valid_record):
    response = client.post("/predict?explain=true", json=valid_record)

    assert response.status_code == 200
    explanation = response.json()["explanation"]
    assert explanation is not None
    assert 0 < len(explanation["top_features"]) <= 10
    assert isinstance(explanation["summary"], str) and explanation["summary"]
    for feature in explanation["top_features"]:
        assert feature["direction"] in {"positive", "negative"}


def test_predict_explanation_works_with_hybrid_serving(hybrid_client, valid_record):
    """The anomaly detector's presence doesn't change what's explained --
    still the classifier's prediction."""
    response = hybrid_client.post("/predict?explain=true", json=valid_record)

    assert response.status_code == 200
    assert response.json()["explanation"] is not None


def test_predict_batch_without_explain_param_leaves_explanations_null(client, fixture_df):
    csv_bytes = fixture_df.to_csv(index=False).encode("utf-8")

    response = client.post(
        "/predict/batch", files={"file": ("sample.csv", io.BytesIO(csv_bytes), "text/csv")}
    )

    assert all(r["explanation"] is None for r in response.json()["results"])


def test_predict_batch_with_explain_true_populates_every_result(client, fixture_df):
    csv_bytes = fixture_df.to_csv(index=False).encode("utf-8")

    response = client.post(
        "/predict/batch?explain=true",
        files={"file": ("sample.csv", io.BytesIO(csv_bytes), "text/csv")},
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == len(fixture_df)
    assert all(r["explanation"] is not None for r in results)
    assert all(len(r["explanation"]["top_features"]) > 0 for r in results)


def test_predict_always_includes_risk_score_even_without_database(client, valid_record):
    """risk scoring/MITRE mapping/alerting always run -- only the DB
    write is opt-in (see database_url on ServingConfig)."""
    response = client.post("/predict", json=valid_record)

    body = response.json()
    assert body["risk_score"]["score"] >= 0.0
    assert body["risk_score"]["severity"] == body["severity"]
    assert sum(body["risk_score"]["factors"].values()) == pytest.approx(body["risk_score"]["score"] / 100)


def test_predict_without_database_configured_writes_nothing(client, valid_record, tmp_path):
    """No database_url -> zero DB writes -- proves persistence is truly
    opt-in, matching every prior milestone's default-off pattern."""
    before = set(tmp_path.rglob("*.db"))

    client.post("/predict", json=valid_record)

    after = set(tmp_path.rglob("*.db"))
    assert before == after


def test_predict_mitre_is_populated_for_attack_category_models(fixture_df, tmp_path):
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        artifact_root=tmp_path / "runs",
        run_name="category-run",
        label_column="attack_category",
    )
    run_training(config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)
    app = create_app(ServingConfig(run_id="category-run", artifact_root=tmp_path / "runs"))
    client = TestClient(app)
    record = {k: fixture_df.iloc[0].to_dict()[k] for k in FEATURE_COLUMNS}

    body = client.post("/predict", json=record).json()

    if body["attack_category"] not in (None, "normal"):
        assert body["mitre"] is not None
        assert body["mitre"]["tactic"]
    else:
        assert body["mitre"] is None


def test_predict_mitre_is_null_for_is_attack_only_models(client, valid_record):
    body = client.post("/predict", json=valid_record).json()
    assert body["mitre"] is None


def test_predict_persists_prediction_when_database_configured(persisted_client, valid_record):
    from nids.api import store

    client, app = persisted_client
    response = client.post("/predict", json=valid_record)
    body = response.json()

    page = store.list_predictions(app.state.db_engine)
    assert page.total == 1
    assert page.items[0].severity == body["severity"]
    assert page.items[0].risk_score == pytest.approx(body["risk_score"]["score"])


def test_predict_alert_id_is_none_below_threshold(persisted_client, valid_record):
    from nids.api import store

    client, app = persisted_client
    # threshold defaults to 70; force it high so nothing crosses it
    app.state.serving_config = ServingConfig(
        run_id=app.state.serving_config.run_id,
        artifact_root=app.state.serving_config.artifact_root,
        database_url=app.state.serving_config.database_url,
        alert_threshold=1000.0,
    )

    body = client.post("/predict", json=valid_record).json()

    assert body["alert_id"] is None
    assert store.list_alerts(app.state.db_engine).total == 0


def test_predict_raises_and_persists_alert_when_threshold_is_low(persisted_client, valid_record):
    from nids.api import store

    client, app = persisted_client
    app.state.serving_config = ServingConfig(
        run_id=app.state.serving_config.run_id,
        artifact_root=app.state.serving_config.artifact_root,
        database_url=app.state.serving_config.database_url,
        alert_threshold=0.0,
    )

    body = client.post("/predict", json=valid_record).json()

    assert body["alert_id"] is not None
    alerts = store.list_alerts(app.state.db_engine)
    assert alerts.total == 1
    assert alerts.items[0].id == body["alert_id"]


def test_predict_batch_persists_every_row_when_database_configured(persisted_client, fixture_df):
    from nids.api import store

    client, app = persisted_client
    csv_bytes = fixture_df.to_csv(index=False).encode("utf-8")

    client.post("/predict/batch", files={"file": ("sample.csv", io.BytesIO(csv_bytes), "text/csv")})

    assert store.list_predictions(app.state.db_engine).total == len(fixture_df)
