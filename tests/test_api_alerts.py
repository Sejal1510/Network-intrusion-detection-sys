from nids.api.alerts import (
    Alert,
    alert_from_dict,
    alert_to_dict,
    generate_alert,
    meets_min_severity,
)
from nids.api.explain import Explanation, FeatureContribution
from nids.api.inference import PredictionResult
from nids.api.mitre import MitreMapping, MitreTechnique
from nids.api.risk import RiskScore


def _result(attack_category=None, prediction=1) -> PredictionResult:
    return PredictionResult(
        prediction=prediction,
        probabilities={"0": 0.1, "1": 0.9},
        confidence=0.9,
        attack_category=attack_category,
        anomaly_score=None,
        is_anomaly=None,
        severity="critical",
    )


def _risk(score: float, severity: str = "critical") -> RiskScore:
    return RiskScore(score=score, severity=severity, factors={"attack_confidence": score / 100})


def test_generate_alert_returns_none_below_threshold():
    alert = generate_alert(_result(), _risk(50.0, "medium"), mitre=None, threshold=70.0)
    assert alert is None


def test_generate_alert_returns_alert_at_or_above_threshold():
    alert = generate_alert(_result(), _risk(75.0, "high"), mitre=None, threshold=70.0)

    assert isinstance(alert, Alert)
    assert alert.risk_score == 75.0


def test_generate_alert_level_matches_risk_score_severity():
    alert = generate_alert(_result(), _risk(95.0, "critical"), mitre=None, threshold=70.0)
    assert alert.level == "critical"


def test_generate_alert_has_a_unique_id_each_time():
    alert_a = generate_alert(_result(), _risk(90.0), mitre=None, threshold=70.0)
    alert_b = generate_alert(_result(), _risk(90.0), mitre=None, threshold=70.0)
    assert alert_a.alert_id != alert_b.alert_id


def test_generate_alert_carries_mitre_mapping_when_given():
    mapping = MitreMapping(
        tactic="Impact",
        techniques=[MitreTechnique(id="T1498", name="Network DoS", url="https://example.com")],
    )
    alert = generate_alert(_result("dos"), _risk(90.0), mitre=mapping, threshold=70.0)
    assert alert.mitre is mapping
    assert alert.attack_category == "dos"


def test_generate_alert_message_includes_explanation_summary_when_given():
    explanation = Explanation(
        base_value=0.1,
        top_features=[
            FeatureContribution(feature="service", value="http", contribution=0.5, direction="positive")
        ],
        summary="Predicted 1 primarily due to: service='http' (+0.50).",
    )
    alert = generate_alert(_result(), _risk(90.0), mitre=None, explanation=explanation, threshold=70.0)

    assert explanation.summary in alert.message


def test_generate_alert_message_degrades_gracefully_without_explanation():
    alert = generate_alert(_result(), _risk(90.0), mitre=None, explanation=None, threshold=70.0)

    assert "CRITICAL" in alert.message
    assert "90" in alert.message


def test_generate_alert_uses_default_threshold_when_not_specified():
    just_below = generate_alert(_result(), _risk(69.9), mitre=None)
    just_above = generate_alert(_result(), _risk(70.0), mitre=None)

    assert just_below is None
    assert just_above is not None


def test_meets_min_severity_true_at_or_above():
    assert meets_min_severity("high", "high") is True
    assert meets_min_severity("critical", "high") is True


def test_meets_min_severity_false_below():
    assert meets_min_severity("medium", "high") is False
    assert meets_min_severity("low", "critical") is False


def test_alert_to_dict_from_dict_round_trips_without_mitre():
    alert = generate_alert(_result(), _risk(90.0), mitre=None, threshold=70.0)

    restored = alert_from_dict(alert_to_dict(alert))

    assert restored == alert


def test_alert_to_dict_from_dict_round_trips_with_mitre():
    mapping = MitreMapping(
        tactic="Impact",
        techniques=[MitreTechnique(id="T1498", name="Network DoS", url="https://example.com")],
    )
    alert = generate_alert(_result("dos"), _risk(90.0), mitre=mapping, threshold=70.0)

    restored = alert_from_dict(alert_to_dict(alert))

    assert restored == alert
    assert restored.mitre == mapping


def test_alert_to_dict_is_json_safe():
    import json

    alert = generate_alert(_result(), _risk(90.0), mitre=None, threshold=70.0)

    # Raises if anything in the dict isn't JSON-serializable (e.g. a raw
    # datetime) -- the whole point of alert_to_dict, since it's what
    # crosses the MessageBus (nids.api.bus, RedisBus JSON-encodes every
    # message).
    json.dumps(alert_to_dict(alert))
