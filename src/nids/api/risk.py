"""Risk scoring: synthesizes a single numeric 0-100 risk score from the
signals `nids.api.inference.PredictionResult` already carries (confidence,
anomaly_score, severity) -- a pure function reusing those fields, never
recomputing prediction/anomaly/severity logic that already ran.

`severity` on `RiskScore` is `PredictionResult.severity` itself (computed
once, by `nids.api.severity.compute_severity`, at prediction time) --
there is exactly one place that decides "how dangerous is this
categorically"; this module only adds a numeric, weighted view on top.
"""

from __future__ import annotations

from dataclasses import dataclass

from nids.api.inference import PredictionResult

# Each component is normalized to [0, 1] before weighting; weights sum to
# 1.0 so the resulting score is always in [0, 100] without needing to
# clip in practice.
_ATTACK_CONFIDENCE_WEIGHT = 0.5
_ANOMALY_WEIGHT = 0.3
_SEVERITY_WEIGHT = 0.2

# Folds the categorical severity judgment back into the numeric score as
# a coarse anchor, without recomputing the rule table that produced it.
_SEVERITY_BANDS = {"low": 0.1, "medium": 0.4, "high": 0.7, "critical": 1.0}


@dataclass(frozen=True)
class RiskScore:
    score: float  # 0-100, higher = more dangerous
    severity: str  # == PredictionResult.severity -- one source of truth
    factors: dict[str, float]  # weighted contributions; sum == score / 100


def _is_attack_result(result: PredictionResult) -> bool:
    """Reads only PredictionResult's already-public fields -- attack_category
    is None exactly for is_attack (binary) models (see
    nids.api.inference._attack_category), never for attack_category
    models, even when they predicted "normal"."""
    if result.attack_category is not None:
        return result.attack_category != "normal"
    return bool(result.prediction)  # is_attack convention: 1 = attack, 0 = normal


def compute_risk_score(result: PredictionResult) -> RiskScore:
    """A confident "normal" verdict contributes nothing to
    `attack_confidence` -- deliberate; a normal-but-suspicious record's
    risk should come from the anomaly component, not from inverting
    confidence (which would conflate "sure it's fine" with "worth
    scoring").

    When no anomaly detector is served (`anomaly_score is None`), that
    component's weight is redistributed proportionally across the other
    two rather than silently dropped, so a classifier-only deployment's
    maximum possible score is still 100, not 70.
    """
    attack_confidence = (
        result.confidence
        if _is_attack_result(result) and result.confidence is not None
        else 0.0
    )
    severity_band = _SEVERITY_BANDS[result.severity]

    if result.anomaly_score is not None:
        weighted = {
            "attack_confidence": _ATTACK_CONFIDENCE_WEIGHT * attack_confidence,
            "anomaly": _ANOMALY_WEIGHT * result.anomaly_score,
            "severity_band": _SEVERITY_WEIGHT * severity_band,
        }
    else:
        remaining = _ATTACK_CONFIDENCE_WEIGHT + _SEVERITY_WEIGHT
        weighted = {
            "attack_confidence": (_ATTACK_CONFIDENCE_WEIGHT / remaining) * attack_confidence,
            "severity_band": (_SEVERITY_WEIGHT / remaining) * severity_band,
        }

    score = 100.0 * min(max(sum(weighted.values()), 0.0), 1.0)
    return RiskScore(score=score, severity=result.severity, factors=weighted)
