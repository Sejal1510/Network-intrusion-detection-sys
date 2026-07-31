"""Model-agnostic evaluation: metrics computed from predictions alone.

This module never touches a model, a feature matrix, or a config — it takes
`y_true` / `y_pred` (and optionally `y_proba`) and returns a plain,
JSON-serializable metrics dict. That keeps it reusable for any classifier
the registry produces and for both the binary (`is_attack`) and multiclass
(`attack_category`) label schemes.
"""

from __future__ import annotations

import warnings
from numbers import Real
from typing import Any

import numpy as np
from sklearn.exceptions import UndefinedMetricWarning
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


def _to_builtin(obj: Any) -> Any:
    """Recursively convert numpy scalars/arrays to native Python types so
    the result is always json.dumps-able."""
    if isinstance(obj, dict):
        return {k: _to_builtin(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_builtin(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return _to_builtin(obj.tolist())
    if isinstance(obj, np.generic):
        return obj.item()
    return obj


def scalar_metrics(metrics: dict[str, Any]) -> dict[str, float]:
    """The plain-number subset of a metrics dict -- excludes nested
    structures like `confusion_matrix`/`classification_report`/`labels`.

    Shared by anything that can only consume flat numeric metrics: MLflow's
    `log_metrics` (see nids.training.tracking) and cross-fold aggregation
    (see nids.training.validation).
    """
    return {
        key: float(value)
        for key, value in metrics.items()
        if isinstance(value, Real) and not isinstance(value, bool)
    }


def evaluate_classifier(
    y_true: Any,
    y_pred: Any,
    y_proba: Any | None = None,
) -> dict[str, Any]:
    """Compute a standard classification metrics dict.

    Works for both binary (`is_attack`) and multiclass (`attack_category`)
    labels: macro/weighted precision/recall/F1 are always computed; a
    binary-averaged precision/recall/F1 and a positive-class ROC-AUC are
    added when exactly two classes are present, and a one-vs-rest macro
    ROC-AUC is added for multiclass when full class probabilities are given.

    ROC-AUC is only defined when both classes/labels actually appear in
    `y_true`; if only one does (e.g. a tiny or pathological sample), the
    corresponding key is simply omitted rather than raising.
    """
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    labels = sorted(set(y_true.tolist()) | set(y_pred.tolist()))

    metrics: dict[str, Any] = {
        "n_samples": len(y_true),
        "labels": labels,
        "accuracy": accuracy_score(y_true, y_pred),
        "precision_macro": precision_score(
            y_true, y_pred, labels=labels, average="macro", zero_division=0
        ),
        "recall_macro": recall_score(
            y_true, y_pred, labels=labels, average="macro", zero_division=0
        ),
        "f1_macro": f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0),
        "precision_weighted": precision_score(
            y_true, y_pred, labels=labels, average="weighted", zero_division=0
        ),
        "recall_weighted": recall_score(
            y_true, y_pred, labels=labels, average="weighted", zero_division=0
        ),
        "f1_weighted": f1_score(
            y_true, y_pred, labels=labels, average="weighted", zero_division=0
        ),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels),
        "classification_report": classification_report(
            y_true, y_pred, labels=labels, output_dict=True, zero_division=0
        ),
    }

    if len(labels) == 2:
        metrics["precision_binary"] = precision_score(
            y_true, y_pred, pos_label=max(labels), average="binary", zero_division=0
        )
        metrics["recall_binary"] = recall_score(
            y_true, y_pred, pos_label=max(labels), average="binary", zero_division=0
        )
        metrics["f1_binary"] = f1_score(
            y_true, y_pred, pos_label=max(labels), average="binary", zero_division=0
        )

    if y_proba is not None and len(labels) >= 2:
        y_proba = np.asarray(y_proba)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=UndefinedMetricWarning)
            try:
                if len(labels) == 2:
                    proba_positive = y_proba if y_proba.ndim == 1 else y_proba[:, -1]
                    auc = roc_auc_score(y_true, proba_positive)
                    if not np.isnan(auc):
                        metrics["roc_auc"] = auc
                elif y_proba.ndim == 2 and y_proba.shape[1] == len(labels):
                    auc = roc_auc_score(
                        y_true, y_proba, multi_class="ovr", average="macro", labels=labels
                    )
                    if not np.isnan(auc):
                        metrics["roc_auc_macro_ovr"] = auc
            except ValueError:
                pass  # AUC undefined for this sample (e.g. degenerate class balance)

    return _to_builtin(metrics)
