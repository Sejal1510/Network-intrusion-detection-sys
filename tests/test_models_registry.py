import numpy as np
import pytest
from catboost import CatBoostClassifier
from sklearn.ensemble import RandomForestClassifier

from nids.models.registry import build_model


def test_build_catboost_applies_seed_and_defaults():
    model = build_model("catboost", random_state=7)
    assert isinstance(model, CatBoostClassifier)
    assert model.get_params()["random_seed"] == 7


def test_build_random_forest_applies_seed_and_defaults():
    model = build_model("random_forest", random_state=7)
    assert isinstance(model, RandomForestClassifier)
    assert model.get_params()["random_state"] == 7


def test_build_unknown_model_raises_with_registry_listed():
    with pytest.raises(ValueError, match="Unknown model 'not_a_model'"):
        build_model("not_a_model")


def test_hyperparams_override_defaults_but_not_seed():
    model = build_model("random_forest", random_state=7, n_estimators=3)
    params = model.get_params()
    assert params["n_estimators"] == 3
    assert params["random_state"] == 7


def test_same_seed_is_deterministic_on_fit_and_predict():
    rng = np.random.RandomState(0)
    X = rng.rand(50, 4)
    y = (X[:, 0] > 0.5).astype(int)

    model_a = build_model("random_forest", random_state=123, n_estimators=10)
    model_b = build_model("random_forest", random_state=123, n_estimators=10)

    model_a.fit(X, y)
    model_b.fit(X, y)

    np.testing.assert_array_equal(model_a.predict(X), model_b.predict(X))
