"""Black-box random-search evasion attack against an already-trained
classifier + its own fitted FeatureEngineer.

Reuses the exact production feature-transform path
(`nids.features.FeatureEngineer.transform`) so what the attack sees is
identical to what `nids.api.inference` would see -- but this module never
imports `nids.api`, never calls a live server, and never changes
production inference, thresholds, or detection behavior. Fully offline:
takes an in-memory model + FeatureEngineer + DataFrame, returns plain
dataclasses.

Binary (`is_attack`) classifiers only for v1 -- attack label is always 1,
normal is always 0. Multiclass (`attack_category`) support would need a
decision about what counts as "evasion" when a row flips to a *different*
attack category rather than to normal; deferred rather than guessed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from nids.evaluation.perturbation import FeatureBounds, perturbation_deltas, sample_perturbation
from nids.features import FeatureEngineer
from nids.models.registry import Classifier

_ATTACK_LABEL = 1
_NORMAL_LABEL = 0


@dataclass(frozen=True)
class AttackResult:
    row_index: Any  # test_df index of the attacked row
    budget: float
    n_trials: int
    baseline_confidence: float  # P(attack) before perturbation
    best_confidence: float  # lowest P(attack) found within budget
    evaded: bool  # did any candidate flip the *predicted label* to normal
    deltas: dict[str, float]  # of the reported (best/evading) candidate


def _attack_probability(model: Classifier, X: np.ndarray) -> np.ndarray:
    proba = model.predict_proba(X)
    class_index = list(model.classes_).index(_ATTACK_LABEL)
    return proba[:, class_index]


def _generate_candidates(
    rows: pd.DataFrame, bounds: FeatureBounds, budget: float, n_trials: int, rng: np.random.Generator
) -> list[pd.Series]:
    """`n_trials` perturbed candidates per row, in row-major order (all of
    row 0's candidates, then all of row 1's, ...) -- callers index back
    into this with `i * n_trials .. (i + 1) * n_trials`."""
    return [
        sample_perturbation(row, bounds, budget, rng)
        for _, row in rows.iterrows()
        for _ in range(n_trials)
    ]


def _attack_at_budget(
    model: Classifier,
    feature_engineer: FeatureEngineer,
    true_positives: pd.DataFrame,
    baseline_confidence: dict[Any, float],
    bounds: FeatureBounds,
    budget: float,
    n_trials: int,
    rng: np.random.Generator,
) -> list[AttackResult]:
    """One budget level, fully vectorized: every row's `n_trials`
    candidates are generated and transformed/predicted in a single batch
    (one `FeatureEngineer.transform` call for the whole budget level, not
    one per row) -- the test sets this runs against are large enough that
    per-row transform calls would dominate runtime."""
    candidates = _generate_candidates(true_positives, bounds, budget, n_trials, rng)
    if not candidates:
        return []

    candidates_df = pd.DataFrame(candidates)
    matrix = feature_engineer.transform(candidates_df)
    predictions = model.predict(matrix.X)
    attack_proba = _attack_probability(model, matrix.X)

    results = []
    for i, (row_index, row) in enumerate(true_positives.iterrows()):
        start, end = i * n_trials, (i + 1) * n_trials
        row_predictions = predictions[start:end]
        row_proba = attack_proba[start:end]
        row_candidates = candidates[start:end]

        evaded_mask = row_predictions == _NORMAL_LABEL
        evaded = bool(evaded_mask.any())
        if evaded:
            masked = np.where(evaded_mask, row_proba, np.inf)
            report_i = int(np.argmin(masked))
        else:
            report_i = int(np.argmin(row_proba))

        results.append(
            AttackResult(
                row_index=row_index,
                budget=budget,
                n_trials=n_trials,
                baseline_confidence=baseline_confidence[row_index],
                best_confidence=float(row_proba[report_i]),
                evaded=evaded,
                deltas=perturbation_deltas(row, row_candidates[report_i]),
            )
        )
    return results


@dataclass(frozen=True)
class AttackRun:
    results: list[AttackResult]
    n_true_positives: int
    n_baseline_negatives: int  # attack rows already misclassified with zero perturbation


def run_attack(
    model: Classifier,
    feature_engineer: FeatureEngineer,
    test_df: pd.DataFrame,
    bounds: FeatureBounds,
    budgets: list[float],
    n_trials: int,
    random_state: int = 42,
    max_rows: int | None = None,
) -> AttackRun:
    """Attack every row of `test_df` the model currently predicts
    correctly as an attack (true positives at baseline), at every budget
    level. Rows the model already misses aren't "evaded" by an
    attacker -- they're already a baseline false negative; both counts are
    returned so callers can report evasion rate alongside baseline FN
    rate (see nids.evaluation.report.evasion_summary).

    `max_rows`: attack at most this many true positives, sampled once
    (deterministically, via `random_state`) before any budget runs -- for
    a fast smoke run against the full test split.
    """
    attack_rows = test_df[test_df["is_attack"] == _ATTACK_LABEL]

    if attack_rows.empty:
        return AttackRun(results=[], n_true_positives=0, n_baseline_negatives=0)

    matrix = feature_engineer.transform(attack_rows)
    predictions = model.predict(matrix.X)
    attack_proba = _attack_probability(model, matrix.X)

    true_positive_mask = predictions == _ATTACK_LABEL
    true_positives = attack_rows[true_positive_mask]
    baseline_confidence = dict(
        zip(true_positives.index, attack_proba[true_positive_mask], strict=True)
    )
    n_baseline_negatives = int((~true_positive_mask).sum())
    n_true_positives_total = len(true_positives)  # before any --max-rows subsampling

    rng = np.random.default_rng(random_state)

    if max_rows is not None and n_true_positives_total > max_rows:
        sampled_positions = rng.choice(n_true_positives_total, size=max_rows, replace=False)
        true_positives = true_positives.iloc[sorted(sampled_positions)]

    results: list[AttackResult] = []
    for budget in budgets:
        results.extend(
            _attack_at_budget(
                model, feature_engineer, true_positives, baseline_confidence, bounds, budget, n_trials, rng
            )
        )

    return AttackRun(
        results=results,
        n_true_positives=n_true_positives_total,
        n_baseline_negatives=n_baseline_negatives,
    )
