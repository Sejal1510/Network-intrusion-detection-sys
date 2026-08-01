"""Isolation Forest as a Classifier: an unsupervised anomaly detector
wrapped to satisfy `nids.models.registry.Classifier`, so it trains,
evaluates, persists, and tunes through the exact same `nids.training`
pipeline as any supervised model -- no anomaly-detection-specific training
code exists anywhere in `nids.training`.

Isolation Forest is unsupervised: `fit(X, y)` ignores `y`. Its native
output (`{-1: anomaly, 1: normal}`) is translated into the `{1: attack, 0:
normal}` space `nids.data.schema`'s `is_attack` label already uses, so
`nids.training.evaluate.evaluate_classifier` (unchanged) produces directly
comparable metrics to any other `is_attack`-trained model. Train this
model with `label_column="is_attack"` only -- anomaly-vs-normal is
inherently binary; it has no `attack_category` notion.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.ensemble import IsolationForest

# Scales IsolationForest's decision_function (typically roughly in
# [-0.5, 0.5]) into a sigmoid's sensitive range before squashing to [0, 1].
# Fixed and batch-independent -- unlike min-max normalization, the same
# input always produces the same anomaly_score regardless of what else is
# in the batch it's scored with.
_SCORE_SCALE = 10.0


class IsolationForestClassifier:
    """Adapts `sklearn.ensemble.IsolationForest` to the `Classifier`
    protocol, plus an additive `anomaly_score` the API's hybrid detection
    layer uses (see `nids.api.inference`)."""

    def __init__(self, random_state: int = 42, **hyperparams: Any) -> None:
        self._model = IsolationForest(random_state=random_state, **hyperparams)

    def fit(self, X: Any, y: Any = None) -> IsolationForestClassifier:
        self._model.fit(X)
        return self

    def predict(self, X: Any) -> np.ndarray:
        raw = self._model.predict(X)  # {-1: anomaly, 1: normal}
        return np.where(raw == -1, 1, 0)  # -> {1: attack, 0: normal}

    def predict_proba(self, X: Any) -> np.ndarray:
        p_attack = self.anomaly_score(X)
        return np.column_stack([1.0 - p_attack, p_attack])

    def anomaly_score(self, X: Any) -> np.ndarray:
        """Normalized anomaly score in [0, 1], higher = more anomalous.

        A fixed sigmoid of `decision_function` -- unlike min-max scaling
        over a batch, a given record always maps to the same score
        regardless of what else it's scored alongside.
        """
        decision = self._model.decision_function(X)
        return 1.0 / (1.0 + np.exp(decision * _SCORE_SCALE))

    @property
    def classes_(self) -> np.ndarray:
        return np.array([0, 1])
