import pytest

from nids.api.inference import PredictionResult
from nids.api.risk import compute_risk_score
from nids.api.severity import compute_severity


def _make_result(
    prediction,
    confidence,
    anomaly_score,
    is_anomaly,
    attack_category=None,
) -> PredictionResult:
    is_attack = attack_category != "normal" if attack_category is not None else bool(prediction)
    severity = compute_severity(is_attack, confidence, is_anomaly)
    probabilities = {"0": 1 - confidence, "1": confidence} if confidence is not None else None
    return PredictionResult(
        prediction=prediction,
        probabilities=probabilities,
        confidence=confidence,
        attack_category=attack_category,
        anomaly_score=anomaly_score,
        is_anomaly=is_anomaly,
        severity=severity,
    )


def test_attack_high_confidence_and_anomalous_scores_high():
    result = _make_result(1, confidence=0.95, anomaly_score=0.9, is_anomaly=True)

    risk = compute_risk_score(result)

    assert risk.severity == "critical"
    assert risk.score > 85


def test_normal_confident_and_not_anomalous_scores_low():
    result = _make_result(0, confidence=0.99, anomaly_score=0.05, is_anomaly=False)

    risk = compute_risk_score(result)

    assert risk.severity == "low"
    assert risk.score < 15


def test_normal_prediction_contributes_no_attack_confidence_regardless_of_confidence():
    result = _make_result(0, confidence=0.99, anomaly_score=None, is_anomaly=None)

    risk = compute_risk_score(result)

    assert risk.factors["attack_confidence"] == 0.0


def test_anomaly_score_influences_risk_even_when_classifier_says_normal():
    calm = _make_result(0, confidence=0.6, anomaly_score=0.05, is_anomaly=False)
    suspicious = _make_result(0, confidence=0.6, anomaly_score=0.95, is_anomaly=True)

    assert compute_risk_score(suspicious).score > compute_risk_score(calm).score


def test_weight_is_redistributed_when_no_anomaly_detector_served():
    result = _make_result(1, confidence=0.95, anomaly_score=None, is_anomaly=None)

    risk = compute_risk_score(result)

    assert "anomaly" not in risk.factors
    assert set(risk.factors) == {"attack_confidence", "severity_band"}
    # max possible score is still 100 without the anomaly component diluting it
    assert risk.score == pytest.approx(100 * (0.5 / 0.7 * 0.95 + 0.2 / 0.7 * 1.0))


@pytest.mark.parametrize(
    ("prediction", "confidence", "anomaly_score", "is_anomaly"),
    [
        (1, 0.95, 0.9, True),
        (0, 0.6, 0.2, False),
        (1, 0.7, None, None),
        (0, None, None, None),
    ],
)
def test_factors_sum_to_score_over_100(prediction, confidence, anomaly_score, is_anomaly):
    result = _make_result(prediction, confidence, anomaly_score, is_anomaly)

    risk = compute_risk_score(result)

    assert sum(risk.factors.values()) == pytest.approx(risk.score / 100)


def test_risk_score_severity_is_exactly_predictionresult_severity_not_recomputed():
    result = _make_result(1, confidence=0.75, anomaly_score=0.4, is_anomaly=False)

    risk = compute_risk_score(result)

    assert risk.severity is result.severity


def test_score_is_bounded_0_to_100():
    for prediction, confidence, anomaly_score, is_anomaly in [
        (1, 1.0, 1.0, True),
        (0, 0.0, 0.0, False),
    ]:
        risk = compute_risk_score(_make_result(prediction, confidence, anomaly_score, is_anomaly))
        assert 0.0 <= risk.score <= 100.0


def test_attack_category_multiclass_normal_prediction_is_not_treated_as_attack():
    result = _make_result(
        "normal", confidence=0.9, anomaly_score=None, is_anomaly=None, attack_category="normal"
    )

    risk = compute_risk_score(result)

    assert risk.factors["attack_confidence"] == 0.0


def test_attack_category_multiclass_attack_prediction_is_treated_as_attack():
    result = _make_result(
        "dos", confidence=0.9, anomaly_score=None, is_anomaly=None, attack_category="dos"
    )

    risk = compute_risk_score(result)

    assert risk.factors["attack_confidence"] > 0.0
