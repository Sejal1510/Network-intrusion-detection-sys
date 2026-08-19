"""Offline adversarial-robustness evaluation (Milestone 17): bounded,
realistic feature-space perturbations against an already-trained NIDS
classifier, using the project's own model and NSL-KDD data only. See
docs/ADVERSARIAL_EVALUATION.md for the full methodology.
"""

from nids.evaluation.attack import AttackResult, AttackRun, run_attack
from nids.evaluation.perturbation import (
    ALL_ALLOWED_FEATURES,
    TIER1_FEATURES,
    TIER2_FEATURES,
    TIER3_FEATURES,
    FeatureBounds,
    perturbation_deltas,
    repair,
    sample_perturbation,
)
from nids.evaluation.report import (
    category_breakdown,
    evasion_summary,
    feature_association,
    shap_overlap,
)

__all__ = [
    "ALL_ALLOWED_FEATURES",
    "TIER1_FEATURES",
    "TIER2_FEATURES",
    "TIER3_FEATURES",
    "AttackResult",
    "AttackRun",
    "FeatureBounds",
    "category_breakdown",
    "evasion_summary",
    "feature_association",
    "perturbation_deltas",
    "repair",
    "run_attack",
    "sample_perturbation",
    "shap_overlap",
]
