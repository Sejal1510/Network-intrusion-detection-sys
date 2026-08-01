import json

import numpy as np
import pytest

from nids.training.evaluate import _flatten_predictions, evaluate_classifier, scalar_metrics


def test_binary_perfect_predictions():
    y_true = [0, 1, 0, 1, 1]
    y_pred = [0, 1, 0, 1, 1]
    y_proba = [0.1, 0.9, 0.2, 0.8, 0.95]

    metrics = evaluate_classifier(y_true, y_pred, y_proba)

    assert metrics["accuracy"] == 1.0
    assert metrics["precision_binary"] == 1.0
    assert metrics["recall_binary"] == 1.0
    assert metrics["f1_binary"] == 1.0
    assert metrics["roc_auc"] == 1.0
    assert metrics["confusion_matrix"] == [[2, 0], [0, 3]]
    assert metrics["labels"] == [0, 1]


def test_binary_with_errors_matches_expected_confusion_matrix():
    y_true = [0, 0, 1, 1]
    y_pred = [0, 1, 1, 0]  # one false positive, one false negative

    metrics = evaluate_classifier(y_true, y_pred)

    assert metrics["accuracy"] == 0.5
    assert metrics["confusion_matrix"] == [[1, 1], [1, 1]]
    assert 0.0 <= metrics["precision_binary"] <= 1.0


def test_multiclass_includes_macro_and_ovr_auc():
    y_true = [0, 1, 2, 0, 1, 2]
    y_pred = [0, 1, 2, 0, 1, 1]
    y_proba = np.array(
        [
            [0.8, 0.1, 0.1],
            [0.1, 0.8, 0.1],
            [0.1, 0.1, 0.8],
            [0.7, 0.2, 0.1],
            [0.2, 0.7, 0.1],
            [0.1, 0.6, 0.3],
        ]
    )

    metrics = evaluate_classifier(y_true, y_pred, y_proba)

    assert metrics["labels"] == [0, 1, 2]
    assert "precision_macro" in metrics
    assert "roc_auc_macro_ovr" in metrics
    assert "precision_binary" not in metrics  # binary-only keys absent for multiclass
    assert len(metrics["confusion_matrix"]) == 3


def test_no_proba_omits_auc_keys():
    metrics = evaluate_classifier([0, 1, 0, 1], [0, 1, 1, 1])
    assert "roc_auc" not in metrics
    assert "roc_auc_macro_ovr" not in metrics


def test_single_class_in_y_true_does_not_raise():
    # degenerate sample: only the "normal" class present; AUC is undefined
    metrics = evaluate_classifier([0, 0, 0], [0, 0, 1], y_proba=[0.1, 0.2, 0.6])
    assert metrics["accuracy"] == pytest.approx(2 / 3)
    assert "roc_auc" not in metrics


def test_output_is_json_serializable():
    y_true = [0, 1, 2, 0, 1, 2]
    y_pred = [0, 1, 2, 0, 2, 2]
    y_proba = np.random.RandomState(0).dirichlet(np.ones(3), size=6)

    metrics = evaluate_classifier(y_true, y_pred, y_proba)

    serialized = json.dumps(metrics)  # must not raise
    reloaded = json.loads(serialized)
    assert reloaded["n_samples"] == 6


def test_flatten_predictions_collapses_column_vector():
    """CatBoost's multiclass predict() shape, reproduced directly."""
    result = _flatten_predictions(np.array([[1], [2], [3]]))

    assert result.shape == (3,)
    np.testing.assert_array_equal(result, [1, 2, 3])


def test_flatten_predictions_leaves_1d_array_unchanged():
    original = np.array([1, 2, 3])

    result = _flatten_predictions(original)

    assert result.shape == (3,)
    np.testing.assert_array_equal(result, original)


def test_handles_catboost_style_2d_column_vector_predictions():
    """Regression test: CatBoost's multiclass predict() returns
    predictions shaped (n_samples, 1) instead of a flat 1D array --
    evaluate_classifier must not crash on that shape (previously:
    `TypeError: unhashable type: 'list'` from `set(y_pred.tolist())` on a
    list of one-element lists)."""
    y_true = np.array(["normal", "dos", "probe", "normal"])
    y_pred = np.array([["normal"], ["dos"], ["dos"], ["normal"]], dtype=object)

    metrics = evaluate_classifier(y_true, y_pred)

    assert metrics["accuracy"] == 0.75
    assert metrics["labels"] == ["dos", "normal", "probe"]


def test_column_vector_predictions_match_equivalent_flat_predictions():
    """Flattening changes representation, never the result."""
    y_true = [0, 1, 2, 0, 1, 2]
    y_pred_flat = [0, 1, 2, 0, 1, 1]
    y_pred_columnar = np.array(y_pred_flat).reshape(-1, 1)

    flat_metrics = evaluate_classifier(y_true, y_pred_flat)
    columnar_metrics = evaluate_classifier(y_true, y_pred_columnar)

    assert flat_metrics == columnar_metrics


def test_scalar_metrics_excludes_nested_structures():
    metrics = evaluate_classifier([0, 1, 0, 1], [0, 1, 1, 1], y_proba=[0.1, 0.9, 0.6, 0.8])

    scalars = scalar_metrics(metrics)

    assert scalars["accuracy"] == metrics["accuracy"]
    assert all(isinstance(v, float) for v in scalars.values())
    assert "confusion_matrix" not in scalars
    assert "classification_report" not in scalars
    assert "labels" not in scalars
