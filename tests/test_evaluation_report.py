from pathlib import Path

import pandas as pd
import pytest

from nids.data import loader
from nids.evaluation.attack import AttackResult, run_attack
from nids.evaluation.perturbation import FeatureBounds
from nids.evaluation.report import (
    category_breakdown,
    evasion_summary,
    feature_association,
    shap_overlap,
)
from nids.training.config import TrainingConfig
from nids.training.core import fit_and_evaluate

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd_cv.txt"


def _result(row_index, budget, evaded, baseline=0.9, best=0.1, deltas=None):
    return AttackResult(
        row_index=row_index,
        budget=budget,
        n_trials=10,
        baseline_confidence=baseline,
        best_confidence=best,
        evaded=evaded,
        deltas=deltas or {},
    )


# ---------------------------------------------------------------------------
# Pure aggregation tests (no model needed)
# ---------------------------------------------------------------------------


def test_evasion_summary_computes_rates_and_baseline_fn():
    results = [
        _result(0, 0.05, evaded=False),
        _result(1, 0.05, evaded=True),
        _result(0, 0.30, evaded=True),
        _result(1, 0.30, evaded=True),
    ]

    summary = evasion_summary(results, n_true_positives=2, n_baseline_negatives=1)

    assert summary["n_true_positives"] == 2
    assert summary["baseline_false_negatives"] == 1
    assert summary["baseline_fn_rate"] == pytest.approx(1 / 3)
    assert summary["per_budget"][0.05]["evasion_rate"] == pytest.approx(0.5)
    assert summary["per_budget"][0.30]["evasion_rate"] == pytest.approx(1.0)
    assert summary["per_budget"][0.05]["mean_confidence_drop"] == pytest.approx(0.8)


def test_evasion_summary_handles_no_results():
    summary = evasion_summary([], n_true_positives=0, n_baseline_negatives=0)

    assert summary["baseline_fn_rate"] == 0.0
    assert summary["per_budget"] == {}


def test_category_breakdown_groups_by_attack_category_and_budget():
    test_df = pd.DataFrame({"attack_category": ["dos", "dos", "probe"]}, index=[0, 1, 2])
    results = [
        _result(0, 0.1, evaded=True),
        _result(1, 0.1, evaded=False),
        _result(2, 0.1, evaded=True),
    ]

    breakdown = category_breakdown(results, test_df)

    assert breakdown[0.1]["dos"]["n"] == 2
    assert breakdown[0.1]["dos"]["n_evaded"] == 1
    assert breakdown[0.1]["dos"]["evasion_rate"] == pytest.approx(0.5)
    assert breakdown[0.1]["probe"]["evasion_rate"] == pytest.approx(1.0)


def test_feature_association_ranks_by_evasion_frequency():
    results = [
        _result(0, 0.1, evaded=True, deltas={"duration": 5.0, "count": 2.0}),
        _result(1, 0.1, evaded=True, deltas={"duration": 3.0}),
        _result(2, 0.1, evaded=False, deltas={"count": 100.0}),  # not evaded -- excluded
    ]

    ranking = feature_association(results)

    assert ranking[0]["feature"] == "duration"
    assert ranking[0]["n_evasions_touched"] == 2
    assert ranking[0]["frequency"] == pytest.approx(1.0)
    assert ranking[0]["mean_abs_delta"] == pytest.approx(4.0)

    count_entry = next(r for r in ranking if r["feature"] == "count")
    assert count_entry["n_evasions_touched"] == 1  # the non-evaded row's delta doesn't count


def test_feature_association_empty_when_no_evasions():
    results = [_result(0, 0.1, evaded=False, deltas={"duration": 1.0})]

    assert feature_association(results) == []


# ---------------------------------------------------------------------------
# shap_overlap: needs a real fitted model + FeatureEngineer
# ---------------------------------------------------------------------------


@pytest.fixture
def fixture_df():
    return loader._read_nsl_kdd_file(FIXTURE)


@pytest.fixture
def fitted(fixture_df):
    config = TrainingConfig(
        model_name="random_forest", model_params={"n_estimators": 20}, label_column="is_attack"
    )
    result = fit_and_evaluate(fixture_df, fixture_df, config)
    return result.model, result.feature_engineer


def test_shap_overlap_reports_per_evaded_row(fixture_df, fitted):
    model, feature_engineer = fitted
    bounds = FeatureBounds.from_train_df(fixture_df)

    attack_run = run_attack(
        model, feature_engineer, fixture_df, bounds, budgets=[0.3], n_trials=15, random_state=3
    )

    overlap = shap_overlap(model, feature_engineer, fixture_df, attack_run.results, top_n=5)

    n_evaded = sum(1 for r in attack_run.results if r.evaded)
    assert overlap["n_evasions"] == n_evaded
    assert len(overlap["per_row"]) == n_evaded
    for entry in overlap["per_row"]:
        assert 0.0 <= entry["overlap_fraction"] <= 1.0
        assert set(entry["overlap_features"]) <= set(entry["top_shap_features"])
        assert set(entry["overlap_features"]) <= set(entry["perturbed_features"])


def test_shap_overlap_empty_when_no_evasions(fixture_df, fitted):
    model, feature_engineer = fitted

    overlap = shap_overlap(model, feature_engineer, fixture_df, [], top_n=5)

    assert overlap == {"n_evasions": 0, "mean_overlap_fraction": 0.0, "per_row": []}
