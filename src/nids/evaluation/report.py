"""Aggregate AttackResult records into JSON-serializable metrics: overall
+ per-budget evasion rate (alongside the baseline false-negative rate for
context), an attack-category breakdown, a per-feature evasion-association
ranking, and how much a successful evasion's touched features overlap with
what SHAP already says the model relies on for that row.

Mirrors nids.training.evaluate's shape (plain dict in, plain dict out) for
everything except `shap_overlap`, which needs the model + FeatureEngineer
to build a `shap.TreeExplainer` -- entirely offline, but the one function
here that isn't a pure aggregation over `AttackResult`.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd
import shap

from nids.data.schema import CATEGORICAL_COLUMNS
from nids.evaluation.attack import AttackResult
from nids.features import FeatureEngineer
from nids.models.registry import Classifier


def _to_builtin(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _to_builtin(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_builtin(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return _to_builtin(obj.tolist())
    if isinstance(obj, np.generic):
        return obj.item()
    return obj


def evasion_summary(
    results: list[AttackResult], n_true_positives: int, n_baseline_negatives: int
) -> dict[str, Any]:
    """Overall + per-budget evasion rate, plus the baseline (unperturbed)
    false-negative rate for context -- an evasion rate can't be judged
    without knowing how many rows the model already misses for free."""
    total_attack_rows = n_true_positives + n_baseline_negatives
    baseline_fn_rate = n_baseline_negatives / total_attack_rows if total_attack_rows else 0.0

    by_budget: dict[float, list[AttackResult]] = defaultdict(list)
    for r in results:
        by_budget[r.budget].append(r)

    per_budget = {}
    for budget, budget_results in sorted(by_budget.items()):
        n = len(budget_results)
        n_evaded = sum(1 for r in budget_results if r.evaded)
        per_budget[budget] = {
            "n_attacked": n,
            "n_evaded": n_evaded,
            "evasion_rate": n_evaded / n if n else 0.0,
            "mean_confidence_drop": (
                float(np.mean([r.baseline_confidence - r.best_confidence for r in budget_results]))
                if n
                else 0.0
            ),
        }

    return _to_builtin(
        {
            "n_true_positives": n_true_positives,
            "baseline_false_negatives": n_baseline_negatives,
            "baseline_fn_rate": baseline_fn_rate,
            "per_budget": per_budget,
        }
    )


def category_breakdown(
    results: list[AttackResult], test_df: pd.DataFrame, category_column: str = "attack_category"
) -> dict[str, Any]:
    """Evasion rate per NSL-KDD attack category (dos/probe/r2l/u2r), per
    budget -- reads `category_column` off `test_df` purely for reporting;
    it's never fed to the model (the model only ever saw `is_attack`)."""
    breakdown: dict[float, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"n": 0, "n_evaded": 0})
    )
    for r in results:
        category = str(test_df.loc[r.row_index, category_column])
        entry = breakdown[r.budget][category]
        entry["n"] += 1
        entry["n_evaded"] += int(r.evaded)

    out = {}
    for budget, categories in sorted(breakdown.items()):
        out[budget] = {
            category: {**stats, "evasion_rate": stats["n_evaded"] / stats["n"] if stats["n"] else 0.0}
            for category, stats in categories.items()
        }
    return _to_builtin(out)


def feature_association(results: list[AttackResult]) -> list[dict[str, Any]]:
    """Ranks allowlisted features by how often they appear in a
    *successful* evasion's perturbation, and the average magnitude of the
    change -- "which knobs did the adversary actually need to turn."""
    counts: dict[str, int] = defaultdict(int)
    magnitude_sums: dict[str, float] = defaultdict(float)
    n_evasions = sum(1 for r in results if r.evaded)

    for r in results:
        if not r.evaded:
            continue
        for feature, delta in r.deltas.items():
            counts[feature] += 1
            magnitude_sums[feature] += abs(delta)

    ranking = [
        {
            "feature": feature,
            "n_evasions_touched": count,
            "frequency": count / n_evasions if n_evasions else 0.0,
            "mean_abs_delta": magnitude_sums[feature] / count,
        }
        for feature, count in counts.items()
    ]
    ranking.sort(key=lambda entry: entry["n_evasions_touched"], reverse=True)
    return _to_builtin(ranking)


def _raw_column_for(transformed_name: str) -> str:
    """Inverse of FeatureEngineer's ColumnTransformer naming -- mirrors
    nids.api.explain._raw_column_for (same ColumnTransformer naming
    contract, duplicated rather than imported to keep this package
    decoupled from nids.api)."""
    _, _, remainder = transformed_name.partition("__")
    for column in CATEGORICAL_COLUMNS:
        if remainder == column or remainder.startswith(f"{column}_"):
            return column
    return remainder


def _attack_class_shap_matrix(explainer: shap.Explainer, X: np.ndarray, model: Classifier) -> np.ndarray:
    """(n_samples, n_features) SHAP contributions for the attack class
    (label 1), normalizing across the shapes shap.TreeExplainer returns
    for different model families -- verified empirically in
    nids.api.explain's module docstring: CatBoost binary already
    (n, f); RandomForestClassifier (n, f, n_classes); older shap versions
    return a list of per-class arrays."""
    raw = explainer.shap_values(X)
    if isinstance(raw, list):
        raw = np.stack(raw, axis=-1)
    raw = np.asarray(raw)
    if raw.ndim == 2:
        return raw
    class_index = list(model.classes_).index(1)
    return raw[:, :, class_index]


def shap_overlap(
    model: Classifier,
    feature_engineer: FeatureEngineer,
    test_df: pd.DataFrame,
    results: list[AttackResult],
    top_n: int = 5,
) -> dict[str, Any]:
    """For every successfully-evaded row, compares that row's *original*
    (pre-perturbation) SHAP top-`top_n` features against the features the
    attack actually perturbed to evade it -- do evasions cluster on the
    features the model already relies on most, or find a side door SHAP
    didn't flag? Builds its own TreeExplainer directly against `model`
    rather than going through nids.api.explain, keeping this package
    decoupled from the serving layer.
    """
    evaded = [r for r in results if r.evaded]
    if not evaded:
        return _to_builtin({"n_evasions": 0, "mean_overlap_fraction": 0.0, "per_row": []})

    rows = test_df.loc[[r.row_index for r in evaded]]
    matrix = feature_engineer.transform(rows)
    explainer = shap.TreeExplainer(model)
    shap_matrix = _attack_class_shap_matrix(explainer, matrix.X, model)
    feature_names_out = feature_engineer.feature_names_out

    per_row = []
    overlap_fractions = []
    for i, result in enumerate(evaded):
        raw_contribs: dict[str, float] = defaultdict(float)
        for name, contribution in zip(feature_names_out, shap_matrix[i], strict=True):
            raw_contribs[_raw_column_for(name)] += float(contribution)
        top_shap_features = {
            feature
            for feature, _ in sorted(raw_contribs.items(), key=lambda kv: abs(kv[1]), reverse=True)[:top_n]
        }

        touched = set(result.deltas)
        overlap = touched & top_shap_features
        fraction = len(overlap) / len(touched) if touched else 0.0
        overlap_fractions.append(fraction)
        per_row.append(
            {
                "row_index": result.row_index,
                "top_shap_features": sorted(top_shap_features),
                "perturbed_features": sorted(touched),
                "overlap_features": sorted(overlap),
                "overlap_fraction": fraction,
            }
        )

    return _to_builtin(
        {
            "n_evasions": len(evaded),
            "mean_overlap_fraction": float(np.mean(overlap_fractions)),
            "per_row": per_row,
        }
    )
