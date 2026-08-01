from pathlib import Path

import numpy as np
import pytest

from nids.api import explain as explain_module
from nids.api.explain import Explanation, FeatureContribution, explain_batch, explain_one
from nids.api.inference import predict_batch, predict_one
from nids.api.model_loader import ServedEnsemble, ServedModel
from nids.data import loader
from nids.training.config import TrainingConfig
from nids.training.core import fit_and_evaluate

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd_cv.txt"


@pytest.fixture
def fixture_df():
    return loader._read_nsl_kdd_file(FIXTURE)


def _build_ensemble(fixture_df, model_name, label_column="is_attack", **model_params):
    config = TrainingConfig(model_name=model_name, label_column=label_column, model_params=model_params)
    result = fit_and_evaluate(fixture_df, fixture_df, config)
    classifier = ServedModel(
        run_id=f"test-{model_name}",
        model=result.model,
        feature_engineer=result.feature_engineer,
        metrics=result.metrics,
        metadata={"model_name": model_name, "label_column": label_column},
    )
    return ServedEnsemble(classifier=classifier, anomaly_detector=None)


# ---------------------------------------------------------------------------
# Pure helper unit tests
# ---------------------------------------------------------------------------


def test_select_row_contributions_handles_2d_array():
    shap_values = np.array([[1.0, 2.0], [3.0, 4.0]])  # (n_samples=2, n_features=2)

    row = explain_module._select_row_contributions(shap_values, row_idx=1, class_index=0)

    np.testing.assert_array_equal(row, [3.0, 4.0])


def test_select_row_contributions_handles_3d_array():
    # (n_samples=2, n_features=2, n_classes=2)
    shap_values = np.array([[[1.0, -1.0], [2.0, -2.0]], [[3.0, -3.0], [4.0, -4.0]]])

    row_class1 = explain_module._select_row_contributions(shap_values, row_idx=1, class_index=1)

    np.testing.assert_array_equal(row_class1, [-3.0, -4.0])


@pytest.mark.parametrize(
    ("expected_value", "class_index", "expected"),
    [
        (0.5, 0, 0.5),  # scalar
        (np.array([0.5]), 1, 0.5),  # 1-element -- always used regardless of class_index
        (np.array([0.3, 0.7]), 1, 0.7),  # per-class
        ([0.3, 0.7], 0, 0.3),  # plain list, per-class
    ],
)
def test_select_class_base_value(expected_value, class_index, expected):
    assert explain_module._select_class_base_value(expected_value, class_index) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("transformed_name", "expected_raw_column"),
    [
        ("numeric__duration", "duration"),
        ("numeric__src_bytes", "src_bytes"),
        ("categorical__protocol_type_tcp", "protocol_type"),
        ("categorical__service_ftp_data", "service"),  # category itself contains an underscore
        ("categorical__flag_S0", "flag"),
    ],
)
def test_raw_column_for(transformed_name, expected_raw_column):
    assert explain_module._raw_column_for(transformed_name) == expected_raw_column


def test_aggregate_to_raw_features_sums_one_hot_subcolumns(fixture_df):
    from nids.features import FeatureEngineer

    fe = FeatureEngineer().fit(fixture_df)
    feature_names = fe.feature_names_out
    shap_row = np.ones(len(feature_names))  # every transformed column contributes exactly 1.0
    raw_record = fixture_df.iloc[0].to_dict()

    contributions = explain_module._aggregate_to_raw_features(feature_names, shap_row, raw_record)

    by_feature = {c.feature: c.contribution for c in contributions}
    n_service_subcolumns = sum(1 for n in feature_names if n.startswith("categorical__service_"))
    assert by_feature["service"] == pytest.approx(n_service_subcolumns)
    assert by_feature["duration"] == pytest.approx(1.0)  # numeric: exactly 1 sub-column


def test_aggregate_to_raw_features_is_sum_preserving(fixture_df):
    """The most important correctness property: regrouping transformed
    columns into raw features must not lose or double-count anything."""
    from nids.features import FeatureEngineer

    fe = FeatureEngineer().fit(fixture_df)
    feature_names = fe.feature_names_out
    rng = np.random.RandomState(0)
    shap_row = rng.uniform(-1, 1, size=len(feature_names))
    raw_record = fixture_df.iloc[0].to_dict()

    contributions = explain_module._aggregate_to_raw_features(feature_names, shap_row, raw_record)

    assert sum(c.contribution for c in contributions) == pytest.approx(shap_row.sum())


def test_aggregate_to_raw_features_carries_the_raw_input_value(fixture_df):
    from nids.features import FeatureEngineer

    fe = FeatureEngineer().fit(fixture_df)
    feature_names = fe.feature_names_out
    shap_row = np.zeros(len(feature_names))
    raw_record = fixture_df.iloc[0].to_dict()

    contributions = explain_module._aggregate_to_raw_features(feature_names, shap_row, raw_record)

    by_feature = {c.feature: c.value for c in contributions}
    assert by_feature["service"] == raw_record["service"]
    assert by_feature["duration"] == raw_record["duration"]


def test_aggregate_to_raw_features_sorts_by_absolute_contribution_desc(fixture_df):
    from nids.features import FeatureEngineer

    fe = FeatureEngineer().fit(fixture_df)
    feature_names = fe.feature_names_out
    rng = np.random.RandomState(1)
    shap_row = rng.uniform(-1, 1, size=len(feature_names))
    raw_record = fixture_df.iloc[0].to_dict()

    contributions = explain_module._aggregate_to_raw_features(feature_names, shap_row, raw_record)

    magnitudes = [abs(c.contribution) for c in contributions]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_direction_matches_contribution_sign(fixture_df):
    from nids.features import FeatureEngineer

    fe = FeatureEngineer().fit(fixture_df)
    feature_names = fe.feature_names_out
    shap_row = np.linspace(-1, 1, len(feature_names))
    raw_record = fixture_df.iloc[0].to_dict()

    contributions = explain_module._aggregate_to_raw_features(feature_names, shap_row, raw_record)

    for c in contributions:
        assert c.direction == ("positive" if c.contribution >= 0 else "negative")


def test_build_summary_names_top_three_features():
    top_features = [
        FeatureContribution(feature="service", value="http", contribution=0.5, direction="positive"),
        FeatureContribution(feature="src_bytes", value=99999, contribution=0.3, direction="positive"),
    ]

    summary = explain_module._build_summary(1, top_features)

    assert "service" in summary
    assert "src_bytes" in summary
    assert "Predicted 1" in summary


def test_build_summary_handles_no_contributors():
    summary = explain_module._build_summary(0, [])
    assert "no strong individual contributors" in summary


# ---------------------------------------------------------------------------
# End-to-end, against every currently-registered model
# ---------------------------------------------------------------------------


def test_explain_one_end_to_end_for_catboost_matches_raw_margin(fixture_df):
    ensemble = _build_ensemble(fixture_df, "catboost", iterations=10, depth=2)
    record = fixture_df.iloc[0].to_dict()
    prediction = predict_one(ensemble, record).prediction

    explanation = explain_one(ensemble, record, prediction)

    assert isinstance(explanation, Explanation)
    assert 0 < len(explanation.top_features) <= 10

    # Full end-to-end additive-consistency check against a named,
    # independently-obtainable ground truth: CatBoost's raw margin.
    matrix = ensemble.classifier.feature_engineer.transform(fixture_df.iloc[[0]])
    raw_margin = ensemble.classifier.model.predict(matrix.X, prediction_type="RawFormulaVal")[0]

    all_features = explain_module._aggregate_to_raw_features(
        ensemble.classifier.feature_engineer.feature_names_out,
        explain_module._select_row_contributions(
            explain_module._to_ndarray(
                explain_module._get_explainer(ensemble.classifier.model).shap_values(matrix.X)
            ),
            0,
            explain_module._class_index(ensemble.classifier.model, prediction),
        ),
        record,
    )
    reconstructed = explanation.base_value + sum(c.contribution for c in all_features)
    assert reconstructed == pytest.approx(raw_margin, abs=1e-6)


def test_explain_one_end_to_end_for_random_forest_matches_predict_proba(fixture_df):
    ensemble = _build_ensemble(fixture_df, "random_forest", n_estimators=5)
    record = fixture_df.iloc[0].to_dict()
    prediction = predict_one(ensemble, record).prediction

    explanation = explain_one(ensemble, record, prediction)

    assert isinstance(explanation, Explanation)
    assert 0 < len(explanation.top_features) <= 10

    matrix = ensemble.classifier.feature_engineer.transform(fixture_df.iloc[[0]])
    class_index = explain_module._class_index(ensemble.classifier.model, prediction)
    proba = ensemble.classifier.model.predict_proba(matrix.X)[0][class_index]

    all_features = explain_module._aggregate_to_raw_features(
        ensemble.classifier.feature_engineer.feature_names_out,
        explain_module._select_row_contributions(
            explain_module._to_ndarray(
                explain_module._get_explainer(ensemble.classifier.model).shap_values(matrix.X)
            ),
            0,
            class_index,
        ),
        record,
    )
    reconstructed = explanation.base_value + sum(c.contribution for c in all_features)
    assert reconstructed == pytest.approx(proba, abs=1e-6)


def test_explain_one_end_to_end_for_isolation_forest(fixture_df):
    ensemble = _build_ensemble(fixture_df, "isolation_forest")
    record = fixture_df.iloc[0].to_dict()
    prediction = predict_one(ensemble, record).prediction

    explanation = explain_one(ensemble, record, prediction)

    assert isinstance(explanation, Explanation)
    assert 0 < len(explanation.top_features) <= 10
    assert all(isinstance(c.feature, str) for c in explanation.top_features)


def test_explain_one_top_features_sorted_descending(fixture_df):
    ensemble = _build_ensemble(fixture_df, "random_forest", n_estimators=5)
    record = fixture_df.iloc[0].to_dict()
    prediction = predict_one(ensemble, record).prediction

    explanation = explain_one(ensemble, record, prediction)

    magnitudes = [abs(c.contribution) for c in explanation.top_features]
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_explain_batch_returns_one_explanation_per_row_in_order(fixture_df):
    ensemble = _build_ensemble(fixture_df, "random_forest", n_estimators=5)
    predictions = [r.prediction for r in predict_batch(ensemble, fixture_df)]

    explanations = explain_batch(ensemble, fixture_df, predictions)

    assert len(explanations) == len(fixture_df)
    assert all(isinstance(e, Explanation) for e in explanations)


def test_explain_one_works_for_attack_category_label_column(fixture_df):
    ensemble = _build_ensemble(fixture_df, "random_forest", label_column="attack_category", n_estimators=5)
    record = fixture_df.iloc[0].to_dict()
    prediction = predict_one(ensemble, record).prediction
    assert isinstance(prediction, str)

    explanation = explain_one(ensemble, record, prediction)

    assert 0 < len(explanation.top_features) <= 10


def test_explainer_is_cached_across_calls(fixture_df):
    ensemble = _build_ensemble(fixture_df, "random_forest", n_estimators=5)

    explainer_a = explain_module._get_explainer(ensemble.classifier.model)
    explainer_b = explain_module._get_explainer(ensemble.classifier.model)

    assert explainer_a is explainer_b
