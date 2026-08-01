import pytest
from pydantic import ValidationError

from nids.api.schemas import (
    BatchPredictResponse,
    BatchPredictSummary,
    ExplanationResponse,
    FeatureContributionResponse,
    HealthResponse,
    MitreMappingResponse,
    MitreTechniqueResponse,
    ModelInfoResponse,
    PredictRequest,
    PredictResponse,
    RiskScoreResponse,
    ServedRunInfo,
)
from nids.data.schema import CATEGORICAL_COLUMNS, FEATURE_COLUMNS


def _valid_record() -> dict:
    record = {col: 0.0 for col in FEATURE_COLUMNS}
    record["protocol_type"] = "tcp"
    record["service"] = "http"
    record["flag"] = "SF"
    return record


def _risk_score(score: float = 10.0, severity: str = "low") -> RiskScoreResponse:
    return RiskScoreResponse(score=score, severity=severity, factors={"attack_confidence": 0.0})


def test_predict_request_fields_match_feature_columns_exactly():
    assert set(PredictRequest.model_fields) == set(FEATURE_COLUMNS)


def test_predict_request_accepts_a_complete_valid_record():
    request = PredictRequest(**_valid_record())

    for col in CATEGORICAL_COLUMNS:
        assert isinstance(getattr(request, col), str)
    assert isinstance(request.duration, float)


def test_predict_request_rejects_missing_field():
    record = _valid_record()
    del record["duration"]

    with pytest.raises(ValidationError):
        PredictRequest(**record)


def test_predict_request_rejects_unknown_extra_field():
    record = _valid_record()
    record["totally_made_up_field"] = 1

    with pytest.raises(ValidationError):
        PredictRequest(**record)


def test_predict_response_hybrid_fields_default_to_none():
    response = PredictResponse(prediction=1, severity="low", risk_score=_risk_score())

    assert response.probabilities is None
    assert response.confidence is None
    assert response.attack_category is None
    assert response.anomaly_score is None
    assert response.is_anomaly is None
    assert response.explanation is None
    assert response.mitre is None
    assert response.alert_id is None


def test_explanation_response_round_trips():
    explanation = ExplanationResponse(
        base_value=0.1,
        top_features=[
            FeatureContributionResponse(
                feature="service", value="http", contribution=0.42, direction="positive"
            ),
        ],
        summary="Predicted 1 primarily due to: service='http' (+0.42).",
    )
    response = PredictResponse(
        prediction=1, severity="high", risk_score=_risk_score(), explanation=explanation
    )

    assert response.explanation.top_features[0].feature == "service"
    assert response.explanation.base_value == 0.1


def test_predict_response_requires_severity():
    with pytest.raises(ValidationError):
        PredictResponse(prediction=1, risk_score=_risk_score())


def test_predict_response_requires_risk_score():
    with pytest.raises(ValidationError):
        PredictResponse(prediction=1, severity="low")


def test_predict_response_carries_mitre_mapping():
    mapping = MitreMappingResponse(
        tactic="Impact",
        techniques=[MitreTechniqueResponse(id="T1498", name="Network DoS", url="https://example.com")],
    )
    response = PredictResponse(
        prediction="dos", severity="high", risk_score=_risk_score(80.0, "high"), mitre=mapping
    )

    assert response.mitre.tactic == "Impact"
    assert response.mitre.techniques[0].id == "T1498"


def test_predict_response_carries_alert_id():
    response = PredictResponse(
        prediction=1, severity="critical", risk_score=_risk_score(95.0, "critical"), alert_id="alert-1"
    )
    assert response.alert_id == "alert-1"


def test_batch_predict_response_round_trips():
    batch = BatchPredictResponse(
        summary=BatchPredictSummary(total_records=2, prediction_counts={"0": 1, "1": 1}),
        results=[
            PredictResponse(prediction=0, severity="low", risk_score=_risk_score()),
            PredictResponse(prediction=1, severity="high", risk_score=_risk_score(75.0, "high")),
        ],
    )
    assert len(batch.results) == 2
    assert batch.summary.total_records == 2


def test_health_response_shape():
    health = HealthResponse(status="ok", model_loaded=True)
    assert health.model_loaded is True


def test_model_info_response_shape():
    info = ModelInfoResponse(
        run_id="run-1",
        model_name="random_forest",
        label_column="is_attack",
        metrics={"accuracy": 0.98},
        metadata={"run_id": "run-1"},
    )
    assert info.metrics["accuracy"] == 0.98
    assert info.anomaly_detector is None


def test_model_info_response_with_anomaly_detector():
    info = ModelInfoResponse(
        run_id="run-1",
        model_name="random_forest",
        metrics={"accuracy": 0.98},
        metadata={},
        anomaly_detector=ServedRunInfo(
            run_id="anomaly-run-1",
            model_name="isolation_forest",
            metrics={"accuracy": 0.9},
            metadata={},
        ),
    )
    assert info.anomaly_detector.run_id == "anomaly-run-1"
