"""Severity: a small, pure rule table combining a classifier's prediction
and confidence with an (optional) anomaly detector's verdict into one
human-facing label.

Deliberately isolated from `nids.api.inference` -- swapping the rule table
later (or making it configurable) never touches prediction logic, and it's
testable as plain input/output without a served model at all.
"""

from __future__ import annotations

_HIGH_CONFIDENCE = 0.9
_MEDIUM_CONFIDENCE = 0.6


def compute_severity(
    is_attack_prediction: bool,
    confidence: float | None,
    is_anomaly: bool | None,
) -> str:
    """Return one of "critical", "high", "medium", "low".

    `is_anomaly` is `None` when no anomaly detector is served -- it only
    ever pushes a classifier-normal verdict up to "medium" (the anomaly
    detector disagreeing is worth a human's attention); it never lowers an
    attack verdict, and a classifier-attack verdict is scored on
    `confidence` alone regardless of `is_anomaly`.
    """
    if is_attack_prediction:
        if confidence is not None and confidence >= _HIGH_CONFIDENCE:
            return "critical"
        if confidence is not None and confidence >= _MEDIUM_CONFIDENCE:
            return "high"
        return "medium"

    if is_anomaly:
        return "medium"
    return "low"
