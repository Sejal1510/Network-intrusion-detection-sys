from pathlib import Path

import numpy as np
import pytest

from nids.data import loader
from nids.evaluation.attack import _generate_candidates, run_attack
from nids.evaluation.perturbation import FeatureBounds
from nids.training.config import TrainingConfig
from nids.training.core import fit_and_evaluate

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd_cv.txt"


@pytest.fixture
def fixture_df():
    return loader._read_nsl_kdd_file(FIXTURE)


@pytest.fixture
def fitted(fixture_df):
    config = TrainingConfig(
        model_name="random_forest",
        model_params={"n_estimators": 20},
        label_column="is_attack",
    )
    result = fit_and_evaluate(fixture_df, fixture_df, config)
    return result.model, result.feature_engineer


@pytest.fixture
def bounds(fixture_df):
    return FeatureBounds.from_train_df(fixture_df)


def test_generate_candidates_is_row_major_n_trials_each(fixture_df, bounds):
    rows = fixture_df.head(3)
    rng = np.random.default_rng(0)

    candidates = _generate_candidates(rows, bounds, budget=0.1, n_trials=4, rng=rng)

    assert len(candidates) == 3 * 4
    # First 4 candidates all derive from row 0's duration, next 4 from row 1's, etc.
    for i, (_, row) in enumerate(rows.iterrows()):
        for candidate in candidates[i * 4 : (i + 1) * 4]:
            assert candidate["protocol_type"] == row["protocol_type"]  # untouched passthrough


def test_run_attack_accounts_for_every_attack_row(fixture_df, fitted, bounds):
    model, feature_engineer = fitted

    attack_run = run_attack(
        model, feature_engineer, fixture_df, bounds, budgets=[0.1], n_trials=5, random_state=42
    )

    n_attack_rows = int((fixture_df["is_attack"] == 1).sum())
    assert attack_run.n_true_positives + attack_run.n_baseline_negatives == n_attack_rows
    assert len(attack_run.results) == attack_run.n_true_positives  # one budget level


def test_run_attack_multiple_budgets_multiplies_results(fixture_df, fitted, bounds):
    model, feature_engineer = fitted

    attack_run = run_attack(
        model, feature_engineer, fixture_df, bounds, budgets=[0.05, 0.15, 0.30], n_trials=5, random_state=42
    )

    assert len(attack_run.results) == attack_run.n_true_positives * 3
    assert {r.budget for r in attack_run.results} == {0.05, 0.15, 0.30}


def test_run_attack_result_fields_are_sane(fixture_df, fitted, bounds):
    model, feature_engineer = fitted

    attack_run = run_attack(
        model, feature_engineer, fixture_df, bounds, budgets=[0.3], n_trials=10, random_state=1
    )

    for result in attack_run.results:
        assert 0.0 <= result.baseline_confidence <= 1.0
        assert 0.0 <= result.best_confidence <= 1.0
        assert result.n_trials == 10
        assert isinstance(result.evaded, bool)
        if result.evaded:
            assert result.best_confidence <= 0.5  # crossed (or tied) the decision boundary
        for delta in result.deltas.values():
            assert delta != 0


def test_run_attack_max_rows_is_deterministic_and_bounded(fixture_df, fitted, bounds):
    model, feature_engineer = fitted

    run_a = run_attack(
        model, feature_engineer, fixture_df, bounds, budgets=[0.1], n_trials=3, random_state=7, max_rows=2
    )
    run_b = run_attack(
        model, feature_engineer, fixture_df, bounds, budgets=[0.1], n_trials=3, random_state=7, max_rows=2
    )

    assert len(run_a.results) == 2
    assert [r.row_index for r in run_a.results] == [r.row_index for r in run_b.results]
    # n_true_positives still reports the *total* true-positive count, not the subsample
    assert run_a.n_true_positives >= 2


def test_run_attack_zero_true_positives_yields_no_results(fixture_df, fitted, bounds):
    model, feature_engineer = fitted
    normal_only = fixture_df[fixture_df["is_attack"] == 0]

    attack_run = run_attack(model, feature_engineer, normal_only, bounds, budgets=[0.1], n_trials=5)

    assert attack_run.results == []
    assert attack_run.n_true_positives == 0
    assert attack_run.n_baseline_negatives == 0
