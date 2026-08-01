"""SHAP-based explanations: a second, independent delegate the API calls
*alongside* `nids.api.inference`, never inside it -- `nids.api.inference`
is unmodified by this module, and explanation is purely additive.

Explains the *predicted* class: "why did the model call this X." Reuses
the served classifier's own fitted `FeatureEngineer` and model -- there is
no separate "explanation model" or "explanation feature pipeline"; this
module independently calls `FeatureEngineer.transform` a second time
(cheap, pure, the one and only feature-engineering implementation --
calling it twice is reuse, not duplication) and consumes the prediction
it's handed rather than recomputing it.

`shap.TreeExplainer`'s output shape genuinely differs by model (verified
empirically against every currently-registered model): CatBoost binary
and this project's `IsolationForestClassifier.explainable_model` return
`(n_samples, n_features)` directly; sklearn's `RandomForestClassifier`
returns `(n_samples, n_features, n_classes)`. `_select_row_contributions`
normalizes this once, branching on array shape (not model name), so a
future tree model needs no special-casing here as long as it fits one of
these two shapes -- and older `shap` versions that return a list of
per-class arrays are normalized to the same 3D convention by `_to_ndarray`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import shap

from nids.api.model_loader import ServedEnsemble, ServedModel
from nids.data.schema import CATEGORICAL_COLUMNS

# How many raw features an Explanation reports, sorted by |contribution|.
# A fixed default rather than a request-configurable value -- YAGNI until
# a real consumer needs otherwise.
_TOP_N = 10


@dataclass(frozen=True)
class FeatureContribution:
    feature: str  # raw feature name, e.g. "service" -- never a one-hot
    # column like "service_http"
    value: Any  # the raw input value for that feature, e.g. "http"
    # Signed SHAP contribution. Units are whichever output space
    # shap.TreeExplainer targets for that model -- verified empirically to
    # differ by model: CatBoost's raw margin/log-odds, sklearn
    # RandomForestClassifier's predicted probability, IsolationForest's
    # internal anomaly score. Not necessarily probability-calibrated, but
    # additive and consistent within one model's own explanations
    # (base_value + sum(all raw features' contributions) reconstructs
    # that model's own output for the explained class/row).
    contribution: float
    direction: str  # "positive" | "negative", derived from sign(contribution)


@dataclass(frozen=True)
class Explanation:
    base_value: float
    top_features: list[FeatureContribution]
    summary: str


def _model_for_shap(model: Any) -> Any:
    """Some `Classifier` adapters (e.g. `IsolationForestClassifier`)
    translate their wrapped model's output space and can't themselves be
    introspected by shap -- those expose `explainable_model` for this.
    Models already shap-ready (CatBoost, RandomForest, used directly)
    need no such indirection."""
    return getattr(model, "explainable_model", model)


_explainer_cache: dict[int, shap.Explainer] = {}


def _get_explainer(model: Any) -> shap.Explainer:
    """Built once per served model and cached for the process's lifetime,
    not per request -- `shap.TreeExplainer` parses the full tree
    structure, which isn't free. Keying by `id(model)` is safe
    specifically because a served model is loaded once at startup (see
    `nids.api.model_loader`) and never replaced in place, so the id is
    stable for as long as the process runs."""
    key = id(model)
    if key not in _explainer_cache:
        _explainer_cache[key] = shap.TreeExplainer(_model_for_shap(model))
    return _explainer_cache[key]


def _to_ndarray(shap_output: Any) -> np.ndarray:
    """Normalizes `TreeExplainer.shap_values`'s return shape across shap
    versions: newer versions return one array; older ones returned a list
    of one array per class. Both become the same convention
    `_select_row_contributions` expects."""
    if isinstance(shap_output, list):
        return np.stack(shap_output, axis=-1)  # -> (n_samples, n_features, n_classes)
    return np.asarray(shap_output)


def _class_index(model: Any, predicted_class: Any) -> int:
    return list(model.classes_).index(predicted_class)


def _select_row_contributions(shap_values: np.ndarray, row_idx: int, class_index: int) -> np.ndarray:
    """One row's per-feature contributions for `class_index`, regardless
    of whether `shap_values` is `(n_samples, n_features)` or
    `(n_samples, n_features, n_classes)`."""
    row = shap_values[row_idx]
    return row[:, class_index] if row.ndim == 2 else row


def _select_class_base_value(expected_value: Any, class_index: int) -> float:
    values = np.atleast_1d(np.asarray(expected_value, dtype=float))
    return float(values[class_index]) if values.shape[0] > 1 else float(values[0])


def _raw_column_for(transformed_name: str) -> str:
    """Inverse of `FeatureEngineer`'s `ColumnTransformer` naming
    (`{transformer}__{column}[_category]`, verified empirically): numeric
    columns come out as `numeric__{column}`; one-hot categorical
    sub-columns come out as `categorical__{column}_{category}`. Matches
    against `nids.data.schema.CATEGORICAL_COLUMNS` explicitly -- never
    guesses a split point, since category values can themselves contain
    underscores (e.g. `service_ftp_data`)."""
    _, _, remainder = transformed_name.partition("__")
    for column in CATEGORICAL_COLUMNS:
        if remainder == column or remainder.startswith(f"{column}_"):
            return column
    return remainder  # numeric column: remainder IS the raw column name


def _aggregate_to_raw_features(
    feature_names_out: list[str], shap_row: np.ndarray, raw_record: dict[str, Any]
) -> list[FeatureContribution]:
    """Sums each raw feature's (possibly many, for one-hot-encoded
    categoricals) transformed-column contributions into one entry per
    `nids.data.schema.FEATURE_COLUMNS` column, paired with that column's
    actual input value (not the scaled/encoded transformed value) -- the
    shape a human or frontend recognizes.

    Returns every raw feature, sorted by `|contribution|` descending;
    callers slice the top N.
    """
    totals: dict[str, float] = {}
    for name, contribution in zip(feature_names_out, shap_row, strict=True):
        raw_column = _raw_column_for(name)
        totals[raw_column] = totals.get(raw_column, 0.0) + float(contribution)

    contributions = [
        FeatureContribution(
            feature=column,
            value=raw_record.get(column),
            contribution=total,
            direction="positive" if total >= 0 else "negative",
        )
        for column, total in totals.items()
    ]
    contributions.sort(key=lambda c: abs(c.contribution), reverse=True)
    return contributions


def _build_summary(prediction: Any, top_features: list[FeatureContribution]) -> str:
    top_three = top_features[:3]
    if not top_three:
        return f"Predicted {prediction!r}: no strong individual contributors."
    reasons = ", ".join(f"{c.feature}={c.value!r} ({c.contribution:+.2f})" for c in top_three)
    return f"Predicted {prediction!r} primarily due to: {reasons}."


def _explain_dataframe(
    classifier: ServedModel, df: pd.DataFrame, predictions: list[Any]
) -> list[Explanation]:
    matrix = classifier.feature_engineer.transform(df)
    explainer = _get_explainer(classifier.model)
    shap_values = _to_ndarray(explainer.shap_values(matrix.X))
    expected_value = explainer.expected_value

    results = []
    for row_idx, prediction in enumerate(predictions):
        class_index = _class_index(classifier.model, prediction)
        row_contributions = _select_row_contributions(shap_values, row_idx, class_index)
        all_features = _aggregate_to_raw_features(
            classifier.feature_engineer.feature_names_out,
            row_contributions,
            df.iloc[row_idx].to_dict(),
        )
        top_features = all_features[:_TOP_N]
        results.append(
            Explanation(
                base_value=_select_class_base_value(expected_value, class_index),
                top_features=top_features,
                summary=_build_summary(prediction, top_features),
            )
        )
    return results


def explain_one(served_ensemble: ServedEnsemble, record: dict[str, Any], prediction: Any) -> Explanation:
    """Explain a single already-computed prediction (from
    `nids.api.inference.predict_one`) for the served classifier."""
    return _explain_dataframe(served_ensemble.classifier, pd.DataFrame([record]), [prediction])[0]


def explain_batch(
    served_ensemble: ServedEnsemble, df: pd.DataFrame, predictions: list[Any]
) -> list[Explanation]:
    """Explain every row of an already-scored batch (from
    `nids.api.inference.predict_batch`), in row order. Computed
    vectorized -- one `shap_values` call for the whole batch's transformed
    matrix, not once per row."""
    return _explain_dataframe(served_ensemble.classifier, df, predictions)
