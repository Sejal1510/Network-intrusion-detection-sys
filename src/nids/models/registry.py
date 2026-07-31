"""Name-keyed model factory: the seam that lets the training pipeline
benchmark additional models without restructuring.

To add a new model (LightGBM, XGBoost, ...): add its dependency to
pyproject.toml, write a `_build_*` factory below that maps `random_state`
onto whatever that library calls its seed parameter, and register it in
`MODEL_REGISTRY`. Nothing else in `nids.training` needs to change.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from catboost import CatBoostClassifier
from sklearn.ensemble import RandomForestClassifier


class Classifier(Protocol):
    """The minimal surface the training pipeline relies on. Any registered
    factory must return an object satisfying this — deliberately just the
    plain scikit-learn estimator interface, so any library that follows it
    (or is wrapped to) works without special-casing."""

    def fit(self, X: Any, y: Any) -> Any: ...
    def predict(self, X: Any) -> Any: ...
    def predict_proba(self, X: Any) -> Any: ...


ModelFactory = Callable[..., Classifier]


def _build_catboost(random_state: int, **hyperparams: Any) -> CatBoostClassifier:
    params = {"verbose": False, "random_seed": random_state, **hyperparams}
    return CatBoostClassifier(**params)


def _build_random_forest(random_state: int, **hyperparams: Any) -> RandomForestClassifier:
    params = {"random_state": random_state, **hyperparams}
    return RandomForestClassifier(**params)


MODEL_REGISTRY: dict[str, ModelFactory] = {
    "catboost": _build_catboost,
    "random_forest": _build_random_forest,
}


def build_model(name: str, random_state: int = 42, **hyperparams: Any) -> Classifier:
    """Construct an unfitted classifier registered under `name`.

    `random_state` is threaded through to whichever seed parameter that
    model's library actually uses, so callers never need to know the
    library-specific name for it.
    """
    try:
        factory = MODEL_REGISTRY[name]
    except KeyError:
        raise ValueError(
            f"Unknown model '{name}'. Registered models: {sorted(MODEL_REGISTRY)}. "
            "To add a new one, register a factory in nids.models.registry."
        ) from None
    return factory(random_state=random_state, **hyperparams)
