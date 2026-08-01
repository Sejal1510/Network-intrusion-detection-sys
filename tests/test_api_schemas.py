import pytest
from pydantic import ValidationError

from nids.api.schemas import (
    BatchPredictResponse,
    BatchPredictSummary,
    HealthResponse,
    ModelInfoResponse,
    PredictRequest,
    PredictResponse,
)
from nids.data.schema import CATEGORICAL_COLUMNS, FEATURE_COLUMNS


def _valid_record() -> dict:
    record = {col: 0.0 for col in FEATURE_COLUMNS}
    record["protocol_type"] = "tcp"
    record["service"] = "http"
    record["flag"] = "SF"
    return record


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


def test_predict_response_probabilities_default_to_none():
    response = PredictResponse(prediction=1)
    assert response.probabilities is None


def test_batch_predict_response_round_trips():
    batch = BatchPredictResponse(
        summary=BatchPredictSummary(total_records=2, prediction_counts={"0": 1, "1": 1}),
        results=[PredictResponse(prediction=0), PredictResponse(prediction=1)],
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
