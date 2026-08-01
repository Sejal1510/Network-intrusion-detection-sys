import pytest

from nids.api.severity import compute_severity


@pytest.mark.parametrize(
    ("is_attack_prediction", "confidence", "is_anomaly", "expected"),
    [
        (True, 0.95, None, "critical"),
        (True, 0.9, False, "critical"),
        (True, 0.75, None, "high"),
        (True, 0.6, True, "high"),
        (True, 0.4, None, "medium"),
        (True, None, None, "medium"),
        (True, 0.99, True, "critical"),  # anomaly agreement never downgrades an attack verdict
        (False, 0.99, True, "medium"),  # classifier says normal, anomaly detector disagrees
        (False, None, True, "medium"),
        (False, 0.99, False, "low"),
        (False, None, None, "low"),  # no anomaly detector served
    ],
)
def test_compute_severity(is_attack_prediction, confidence, is_anomaly, expected):
    assert compute_severity(is_attack_prediction, confidence, is_anomaly) == expected
