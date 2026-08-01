import numpy as np
import pytest

from nids.models.anomaly import IsolationForestClassifier
from nids.models.registry import build_model


@pytest.fixture
def separable_data():
    """A tight normal cluster plus a handful of far-away outliers, split
    into a train set (cluster only, unlabeled -- as real training would be
    dominated by normal traffic) and an eval set containing both."""
    rng = np.random.RandomState(0)
    normal = rng.normal(loc=0.0, scale=0.1, size=(100, 4))
    outliers = rng.normal(loc=10.0, scale=0.1, size=(10, 4))

    X_train = normal
    X_eval = np.vstack([normal[:20], outliers])
    y_eval = np.array([0] * 20 + [1] * len(outliers))
    return X_train, X_eval, y_eval


def test_build_isolation_forest_returns_the_adapter():
    model = build_model("isolation_forest", random_state=7)
    assert isinstance(model, IsolationForestClassifier)


def test_fit_ignores_y_and_returns_self(separable_data):
    X_train, _, _ = separable_data
    model = IsolationForestClassifier(random_state=42)

    result = model.fit(X_train, y=np.zeros(len(X_train)))

    assert result is model


def test_predict_labels_outliers_as_attack_and_inliers_as_normal(separable_data):
    X_train, X_eval, y_eval = separable_data
    model = IsolationForestClassifier(random_state=42, contamination=0.1).fit(X_train)

    predictions = model.predict(X_eval)

    assert set(predictions.tolist()) <= {0, 1}
    # every outlier is flagged; normal points are overwhelmingly not
    assert predictions[y_eval == 1].mean() > 0.8
    assert predictions[y_eval == 0].mean() < 0.2


def test_anomaly_score_is_higher_for_outliers_than_inliers(separable_data):
    X_train, X_eval, y_eval = separable_data
    model = IsolationForestClassifier(random_state=42).fit(X_train)

    scores = model.anomaly_score(X_eval)

    assert scores.min() >= 0.0
    assert scores.max() <= 1.0
    assert scores[y_eval == 1].mean() > scores[y_eval == 0].mean()


def test_predict_proba_is_two_column_and_sums_to_one(separable_data):
    X_train, X_eval, _ = separable_data
    model = IsolationForestClassifier(random_state=42).fit(X_train)

    proba = model.predict_proba(X_eval)

    assert proba.shape == (len(X_eval), 2)
    np.testing.assert_allclose(proba.sum(axis=1), 1.0)
    np.testing.assert_allclose(proba[:, 1], model.anomaly_score(X_eval))


def test_classes_are_fixed_binary_labels():
    model = IsolationForestClassifier(random_state=42)
    np.testing.assert_array_equal(model.classes_, [0, 1])


def test_explainable_model_exposes_the_inner_sklearn_estimator(separable_data):
    from sklearn.ensemble import IsolationForest

    X_train, _, _ = separable_data
    model = IsolationForestClassifier(random_state=42).fit(X_train)

    assert isinstance(model.explainable_model, IsolationForest)
    assert model.explainable_model is model._model


def test_same_seed_is_deterministic_on_fit_and_predict(separable_data):
    X_train, X_eval, _ = separable_data

    model_a = IsolationForestClassifier(random_state=123).fit(X_train)
    model_b = IsolationForestClassifier(random_state=123).fit(X_train)

    np.testing.assert_array_equal(model_a.predict(X_eval), model_b.predict(X_eval))
