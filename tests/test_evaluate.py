import json

import numpy as np
import pytest

from nids.training.evaluate import evaluate_classifier, scalar_metrics


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


def test_scalar_metrics_excludes_nested_structures():
    metrics = evaluate_classifier([0, 1, 0, 1], [0, 1, 1, 1], y_proba=[0.1, 0.9, 0.6, 0.8])

    scalars = scalar_metrics(metrics)

    assert scalars["accuracy"] == metrics["accuracy"]
    assert all(isinstance(v, float) for v in scalars.values())
    assert "confusion_matrix" not in scalars
    assert "classification_report" not in scalars
    assert "labels" not in scalars
