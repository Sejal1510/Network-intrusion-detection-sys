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


def test_health_reports_database_not_configured_by_default(client):
    assert client.get("/health").json()["database_configured"] is False


def test_health_reports_database_configured_when_database_url_set(persisted_client):
    client, _app = persisted_client
    assert client.get("/health").json()["database_configured"] is True


def test_cors_headers_absent_by_default(client):
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert "access-control-allow-origin" not in response.headers


def test_cors_headers_present_when_origin_configured(fixture_df, tmp_path):
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        artifact_root=tmp_path / "runs",
        run_name="cors-fixture-run",
    )
    run_training(config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)

    serving_config = ServingConfig(
        run_id="cors-fixture-run",
        artifact_root=tmp_path / "runs",
        cors_origins=("http://localhost:5173",),
    )
    app = create_app(serving_config)
    client = TestClient(app)

    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_get_mitre_returns_full_mapping_table(client):
    response = client.get("/mitre")

    assert response.status_code == 200
    body = response.json()
    assert "normal" not in body
    for category in ("dos", "probe", "r2l", "u2r"):
        assert category in body
        assert body[category]["tactic"]
        assert len(body[category]["techniques"]) > 0


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


def test_predict_increments_alerts_raised_total_when_alert_worthy(persisted_client, valid_record):
    client, app = persisted_client
    app.state.serving_config = ServingConfig(
        run_id=app.state.serving_config.run_id,
        artifact_root=app.state.serving_config.artifact_root,
        database_url=app.state.serving_config.database_url,
        alert_threshold=0.0,
    )

    client.post("/predict", json=valid_record)

    assert app.state.metrics.alerts_raised_total.labels(source="api")._value.get() == 1


def test_predict_does_not_increment_alerts_raised_total_below_threshold(persisted_client, valid_record):
    client, app = persisted_client
    app.state.serving_config = ServingConfig(
        run_id=app.state.serving_config.run_id,
        artifact_root=app.state.serving_config.artifact_root,
        database_url=app.state.serving_config.database_url,
        alert_threshold=1000.0,
    )

    client.post("/predict", json=valid_record)

    assert app.state.metrics.alerts_raised_total.labels(source="api")._value.get() == 0


def test_predict_batch_persists_every_row_when_database_configured(persisted_client, fixture_df):
    from nids.api import store

    client, app = persisted_client
    csv_bytes = fixture_df.to_csv(index=False).encode("utf-8")

    client.post("/predict/batch", files={"file": ("sample.csv", io.BytesIO(csv_bytes), "text/csv")})

    assert store.list_predictions(app.state.db_engine).total == len(fixture_df)


def test_predict_batch_increments_alerts_raised_total_per_alerting_row(persisted_client, fixture_df):
    client, app = persisted_client
    app.state.serving_config = ServingConfig(
        run_id=app.state.serving_config.run_id,
        artifact_root=app.state.serving_config.artifact_root,
        database_url=app.state.serving_config.database_url,
        alert_threshold=0.0,
    )
    csv_bytes = fixture_df.to_csv(index=False).encode("utf-8")

    client.post("/predict/batch", files={"file": ("sample.csv", io.BytesIO(csv_bytes), "text/csv")})

    assert app.state.metrics.alerts_raised_total.labels(source="api")._value.get() == len(fixture_df)


def test_predict_returns_429_after_exceeding_inference_rate_limit(persisted_client, valid_record):
    client, app = persisted_client
    app.state.serving_config = ServingConfig(
        run_id=app.state.serving_config.run_id,
        artifact_root=app.state.serving_config.artifact_root,
        database_url=app.state.serving_config.database_url,
        inference_rate_limit_per_minute=1,
    )

    first = client.post("/predict", json=valid_record)
    second = client.post("/predict", json=valid_record)

    assert first.status_code == 200
    assert second.status_code == 429


def test_predict_batch_returns_429_after_exceeding_inference_rate_limit(persisted_client, fixture_df):
    client, app = persisted_client
    app.state.serving_config = ServingConfig(
        run_id=app.state.serving_config.run_id,
        artifact_root=app.state.serving_config.artifact_root,
        database_url=app.state.serving_config.database_url,
        inference_rate_limit_per_minute=1,
    )
    csv_bytes = fixture_df.to_csv(index=False).encode("utf-8")

    first = client.post(
        "/predict/batch", files={"file": ("sample.csv", io.BytesIO(csv_bytes), "text/csv")}
    )
    second = client.post(
        "/predict/batch", files={"file": ("sample.csv", io.BytesIO(csv_bytes), "text/csv")}
    )

    assert first.status_code == 200
    assert second.status_code == 429


def test_predict_rate_limit_rejection_is_not_persisted_as_audit_event(persisted_client, valid_record):
    from nids.api import store

    client, app = persisted_client
    app.state.serving_config = ServingConfig(
        run_id=app.state.serving_config.run_id,
        artifact_root=app.state.serving_config.artifact_root,
        database_url=app.state.serving_config.database_url,
        inference_rate_limit_per_minute=1,
    )

    client.post("/predict", json=valid_record)
    client.post("/predict", json=valid_record)  # rejected with 429

    assert store.list_audit_events(app.state.db_engine).total == 0


def test_predict_batch_returns_413_when_upload_exceeds_max_size(persisted_client, fixture_df):
    client, app = persisted_client
    app.state.serving_config = ServingConfig(
        run_id=app.state.serving_config.run_id,
        artifact_root=app.state.serving_config.artifact_root,
        database_url=app.state.serving_config.database_url,
        max_upload_size_bytes=10,
    )
    csv_bytes = fixture_df.to_csv(index=False).encode("utf-8")

    response = client.post(
        "/predict/batch", files={"file": ("sample.csv", io.BytesIO(csv_bytes), "text/csv")}
    )

    assert response.status_code == 413


def test_predict_with_slack_configured_notifies_on_critical_alert(fixture_df, valid_record, tmp_path, monkeypatch):
    """End-to-end: a real app, with a real (mocked-at-the-HTTP-boundary)
    Slack channel configured, actually gets a POST out of a critical
    /predict call -- config -> nids.api.app.build_channels ->
    _lifespan's dispatcher startup -> _notify -> the "notifications" bus
    channel -> the dispatcher -> SlackNotificationChannel.send, all real
    except the final `requests.post`. Needs `with TestClient(app) as
    client:` (unlike the module's plain `client` fixture) so `_lifespan`
    -- and therefore the dispatcher task -- actually runs."""
    posted = []

    def fake_post(url, json, timeout):
        posted.append((url, json))

        class FakeResponse:
            def raise_for_status(self):
                pass

        return FakeResponse()

    monkeypatch.setattr("nids.api.notifications.slack.requests.post", fake_post)

    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 5},
        artifact_root=tmp_path / "runs",
        run_name="slack-fixture-run",
    )
    run_training(config, train_df=fixture_df, test_df=fixture_df, log_to_mlflow=False)

    serving_config = ServingConfig(
        run_id="slack-fixture-run",
        artifact_root=tmp_path / "runs",
        alert_threshold=0.0,
        notification_min_severity="low",
        slack_webhook_url="https://hooks.slack.example/T000/B000/xxx",
    )
    app = create_app(serving_config)

    with TestClient(app) as client:
        response = client.post("/predict", json=valid_record)
        assert response.status_code == 200
        assert response.json()["alert_id"] is not None

        # The dispatcher runs as a background asyncio task; give the
        # event loop a beat to run it after the synchronous /predict
        # call returns.
        import time

        for _ in range(50):
            if posted:
                break
            time.sleep(0.02)

    assert len(posted) == 1
    assert posted[0][0] == "https://hooks.slack.example/T000/B000/xxx"


@pytest.fixture
def authenticated_client(fixture_df, tmp_path):
    """A client with database_url configured (CurrentUserDep needs a
    db_engine to look up sessions) and a logged-in session already
    attached -- same pattern test_api_history.py's `client` fixture
    uses, for /rules and /metrics/summary (both login-gated, unlike
    /mitre and /metrics)."""
    from nids.api.user_auth import create_session, register_user

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
        database_url=f"sqlite:///{tmp_path / 'auth.db'}",
    )
    app = create_app(serving_config)
    test_client = TestClient(app)
    user = register_user(app.state.db_engine, "analyst1", "hunter2", "analyst")
    session = create_session(app.state.db_engine, user.id, ttl_seconds=3600)
    test_client.headers.update({"Authorization": f"Bearer {session.token}"})
    return test_client, app


def test_rules_requires_authentication(persisted_client):
    """A database-configured but unauthenticated client -- with no
    db_engine at all (the plain `client` fixture), CurrentUserDep 503s
    before it ever gets to check for a token; this exercises the actual
    401 path, matching test_api_history.py's unauthenticated_client
    pattern."""
    test_client, _ = persisted_client
    response = test_client.get("/rules")
    assert response.status_code == 401


def test_rules_returns_the_configured_rules(authenticated_client):
    test_client, _ = authenticated_client

    response = test_client.get("/rules")

    assert response.status_code == 200
    body = response.json()
    assert len(body) >= 4
    ids = [r["id"] for r in body]
    assert "R001" in ids
    r001 = next(r for r in body if r["id"] == "R001")
    assert r001["severity"] == "critical"
    assert r001["conditions"]
    assert r001["mitre"]["tactic"] == "Impact"


def test_metrics_summary_requires_authentication(persisted_client):
    test_client, _ = persisted_client
    response = test_client.get("/metrics/summary")
    assert response.status_code == 401


def test_metrics_summary_reflects_real_activity(authenticated_client, valid_record):
    test_client, _ = authenticated_client

    test_client.post("/predict", json=valid_record)

    response = test_client.get("/metrics/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["http_requests_total"] >= 1
    assert "/predict" in body["predictions_by_route"]
    assert body["predictions_by_route"]["/predict"] >= 1
