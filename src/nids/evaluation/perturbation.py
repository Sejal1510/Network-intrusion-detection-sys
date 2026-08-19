"""Bounded, realistic feature-space perturbations for adversarial
robustness evaluation (Milestone 17).

Pure data transforms only -- no model, no I/O beyond the training split
passed in to fit Tier-1 bounds. Full methodology and the rationale behind
each tier/exclusion lives in docs/ADVERSARIAL_EVALUATION.md; this module is
the allowlist + bounds + constraint-repair implementation of that document.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Tier 1: attacker directly crafts these at the packet/flow-shaping level.
# Perturbed both up and down, bounded to the *training* split's observed
# [min, max] (never the test split being attacked -- see FeatureBounds).
TIER1_FEATURES: list[str] = [
    "duration",
    "src_bytes",
    "wrong_fragment",
    "urgent",
    "count",
    "srv_count",
    "dst_host_count",
    "dst_host_srv_count",
]

# Tier 2: rate features in [0, 1], attacker-influenced via traffic shaping
# rather than directly set (they're computed from a windowed aggregate of
# surrounding connections, not just this row -- attacking them per-row in
# isolation is a documented simplification). Bounded absolutely to [0, 1].
TIER2_FEATURES: list[str] = [
    "serror_rate",
    "srv_serror_rate",
    "rerror_rate",
    "srv_rerror_rate",
    "same_srv_rate",
    "diff_srv_rate",
    "srv_diff_host_rate",
    "dst_host_same_srv_rate",
    "dst_host_diff_srv_rate",
    "dst_host_same_src_port_rate",
    "dst_host_srv_diff_host_rate",
    "dst_host_serror_rate",
    "dst_host_srv_serror_rate",
    "dst_host_rerror_rate",
    "dst_host_srv_rerror_rate",
]

# Tier 3: activity-count "footprint" features. An attacker can plausibly
# suppress these (do less) but fabricating them upward isn't a realistic
# evasion move without a materially different attack -- decrease-only,
# floored at 0, budgeted as a fraction of the row's own original value.
TIER3_FEATURES: list[str] = [
    "num_file_creations",
    "num_shells",
    "num_access_files",
    "num_root",
    "hot",
    "num_failed_logins",
]

ALL_ALLOWED_FEATURES: list[str] = [*TIER1_FEATURES, *TIER2_FEATURES, *TIER3_FEATURES]

# Excluded, deliberately: protocol_type/service/flag (categorical, per
# explicit instruction -- no attack-specific carve-out in v1), land
# (defines the land-attack itself), logged_in/root_shell/su_attempted
# (attack-success outcomes, not attacker "dials"), is_host_login/
# is_guest_login (account identity), num_compromised (outcome count),
# num_outbound_cmds (constant 0 in NSL-KDD), dst_bytes (server-controlled
# response size, only indirectly attacker-influenced).

_INTEGER_FEATURES = frozenset([*TIER1_FEATURES, *TIER3_FEATURES])

# (feature expected >=, feature expected <=) -- repaired by clipping the
# smaller-side feature down to the larger-side one.
_LE_INVARIANTS: list[tuple[str, str]] = [
    ("count", "srv_count"),
    ("dst_host_count", "dst_host_srv_count"),
]

# Rate pairs whose sum shouldn't exceed 1.0 under the original KDD
# definitions -- repaired by proportionally rescaling both down.
_SUM_LE_ONE_INVARIANTS: list[tuple[str, str]] = [
    ("same_srv_rate", "diff_srv_rate"),
    ("dst_host_same_srv_rate", "dst_host_diff_srv_rate"),
    ("serror_rate", "rerror_rate"),
    ("srv_serror_rate", "srv_rerror_rate"),
    ("dst_host_serror_rate", "dst_host_rerror_rate"),
    ("dst_host_srv_serror_rate", "dst_host_srv_rerror_rate"),
]


@dataclass(frozen=True)
class FeatureBounds:
    """Per-Tier-1-feature [min, upper] observed on the *training* split
    only -- never the test split being attacked, so bounds aren't fit on
    the same data the attack is evaluated against.

    `upper` is a high quantile, not the raw max: NSL-KDD's `src_bytes` has
    a training-split max of ~1.38 billion against a 99.9th percentile of
    ~2.2 million (a handful of known data-quality outlier rows) -- a raw
    min/max bound would let a "5% of range" budget move `src_bytes` by
    tens of millions, which isn't a bounded, realistic perturbation by any
    reading of that phrase. A high quantile keeps the budget anchored to
    the training distribution's actual bulk while still allowing genuinely
    large legitimate values (e.g. `count`/`srv_count`/`dst_host_count`,
    whose 99.9th percentile already equals their max -- KDD caps those at
    511/511/255 by construction, so this changes nothing for them)."""

    tier1_bounds: dict[str, tuple[float, float]]

    @classmethod
    def from_train_df(cls, train_df: pd.DataFrame, upper_quantile: float = 0.999) -> FeatureBounds:
        bounds = {
            feature: (
                float(train_df[feature].min()),
                float(train_df[feature].quantile(upper_quantile)),
            )
            for feature in TIER1_FEATURES
        }
        return cls(tier1_bounds=bounds)


def _clip(value: float, lo: float, hi: float) -> float:
    return min(max(value, lo), hi)


def repair(row: pd.Series) -> pd.Series:
    """Enforce the small set of "obvious feature relationships" a bounded
    perturbation must not break. Repairs by clipping/rescaling in place,
    never by rejecting and resampling -- a deliberate simplicity choice,
    documented in docs/ADVERSARIAL_EVALUATION.md."""
    row = row.copy()
    for upper, lower in _LE_INVARIANTS:
        row[lower] = min(row[lower], row[upper])
    for a, b in _SUM_LE_ONE_INVARIANTS:
        total = row[a] + row[b]
        if total > 1.0:
            scale = 1.0 / total
            row[a] *= scale
            row[b] *= scale
    return row


def sample_perturbation(
    row: pd.Series, bounds: FeatureBounds, epsilon: float, rng: np.random.Generator
) -> pd.Series:
    """One random candidate: every allowlisted feature independently
    offset within its epsilon-scaled budget window, clipped to that
    feature's bounds, then repaired. `row` is a raw (pre-FeatureEngineer)
    record; every non-allowlisted column (including protocol_type/service/
    flag) passes through unchanged."""
    candidate = row.copy()

    for feature in TIER1_FEATURES:
        lo, hi = bounds.tier1_bounds[feature]
        original = float(row[feature])
        # The clip ceiling never drops below the row's own original value:
        # `hi` is a training-split quantile (see FeatureBounds), so a row
        # whose real value already exceeds it (a legitimate large outlier)
        # must not get silently shrunk by an unlucky (small/negative) delta.
        clip_hi = max(hi, original)
        window = epsilon * (hi - lo)
        delta = rng.uniform(-window, window) if window > 0 else 0.0
        candidate[feature] = _clip(original + delta, lo, clip_hi)

    for feature in TIER2_FEATURES:
        delta = rng.uniform(-epsilon, epsilon)
        candidate[feature] = _clip(float(row[feature]) + delta, 0.0, 1.0)

    for feature in TIER3_FEATURES:
        original = float(row[feature])
        max_decrease = epsilon * original
        delta = rng.uniform(-max_decrease, 0.0) if max_decrease > 0 else 0.0
        candidate[feature] = _clip(original + delta, 0.0, original)

    for feature in _INTEGER_FEATURES:
        candidate[feature] = round(candidate[feature])

    return repair(candidate)


def perturbation_deltas(original: pd.Series, perturbed: pd.Series) -> dict[str, float]:
    """Nonzero (feature -> delta) for every allowlisted feature that
    actually changed -- feeds the per-feature evasion-association report."""
    deltas = {}
    for feature in ALL_ALLOWED_FEATURES:
        delta = float(perturbed[feature]) - float(original[feature])
        if delta != 0:
            deltas[feature] = delta
    return deltas
