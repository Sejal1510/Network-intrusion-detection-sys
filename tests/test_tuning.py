from pathlib import Path

import pytest

from nids.data import loader
from nids.training import tuning as tuning_module
from nids.training.config import TrainingConfig
from nids.training.search import GridSearch, RandomSearch
from nids.training.tuning import TuningResult, search_hyperparameters

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd_cv.txt"


@pytest.fixture
def cv_df():
    return loader._read_nsl_kdd_file(FIXTURE)


def test_search_hyperparameters_evaluates_every_grid_candidate(cv_df):
    config = TrainingConfig(model_name="random_forest", cv_folds=3)
    space = {"n_estimators": [5, 10], "max_depth": [2, 4]}

    result = search_hyperparameters(config, space, GridSearch(), df=cv_df)

    assert isinstance(result, TuningResult)
    assert len(result.trials) == 4
    assert result.strategy_name == "GridSearch"
    seen_params = {frozenset(trial.params.items()) for trial in result.trials}
    assert seen_params == {
        frozenset({("n_estimators", 5), ("max_depth", 2)}),
        frozenset({("n_estimators", 5), ("max_depth", 4)}),
        frozenset({("n_estimators", 10), ("max_depth", 2)}),
        frozenset({("n_estimators", 10), ("max_depth", 4)}),
    }


def test_search_hyperparameters_selects_best_by_metric_and_direction(cv_df):
    config = TrainingConfig(model_name="random_forest", cv_folds=3)
    space = {"n_estimators": [5, 10]}

    result_max = search_hyperparameters(
        config, space, GridSearch(), df=cv_df, metric="accuracy", maximize=True
    )
    result_min = search_hyperparameters(
        config, space, GridSearch(), df=cv_df, metric="accuracy", maximize=False
    )

    best_scores = [t.score for t in result_max.trials]
    assert result_max.best_trial.score == max(best_scores)
    assert result_min.best_trial.score == min(best_scores)


def test_search_hyperparameters_merges_candidate_into_base_model_params(cv_df):
    config = TrainingConfig(
        model_name="random_forest", model_params={"n_estimators": 5, "min_samples_leaf": 2}
    )
    space = {"n_estimators": [7]}  # overrides base's n_estimators=5

    result = search_hyperparameters(config, space, GridSearch(), df=cv_df)

    trial_params = result.trials[0].config.model_params
    assert trial_params["n_estimators"] == 7  # candidate wins
    assert trial_params["min_samples_leaf"] == 2  # base value preserved


def test_search_hyperparameters_trial_run_names_are_deterministic_and_unique(cv_df):
    config = TrainingConfig(model_name="random_forest", cv_folds=3)
    space = {"n_estimators": [5, 10, 15]}

    result = search_hyperparameters(config, space, GridSearch(), df=cv_df)

    run_names = [t.config.run_name for t in result.trials]
    assert len(set(run_names)) == len(run_names)  # all unique
    assert all(name.startswith(result.study_run_id) for name in run_names)


def test_search_hyperparameters_rejects_metric_absent_from_evaluation(cv_df):
    config = TrainingConfig(model_name="random_forest", cv_folds=3)
    space = {"n_estimators": [5]}

    with pytest.raises(ValueError, match="not_a_real_metric"):
        search_hyperparameters(config, space, GridSearch(), df=cv_df, metric="not_a_real_metric")


def test_search_hyperparameters_raises_on_empty_search_space_candidates(cv_df, monkeypatch):
    config = TrainingConfig(model_name="random_forest", cv_folds=3)

    class EmptyStrategy:
        def generate_candidates(self, search_space):
            return []

    with pytest.raises(ValueError, match="zero candidates"):
        search_hyperparameters(config, {"n_estimators": [5]}, EmptyStrategy(), df=cv_df)


def test_search_hyperparameters_loads_data_once_when_df_omitted(cv_df, monkeypatch):
    call_count = {"n": 0}

    def fake_load_train(full):
        call_count["n"] += 1
        return cv_df

    monkeypatch.setattr(tuning_module, "load_train", fake_load_train)

    config = TrainingConfig(model_name="random_forest", cv_folds=3)
    space = {"n_estimators": [5, 10, 15]}  # 3 trials

    search_hyperparameters(config, space, GridSearch())

    assert call_count["n"] == 1  # loaded once, reused across all 3 trials


def test_search_hyperparameters_is_deterministic_with_random_search(cv_df):
    config = TrainingConfig(model_name="random_forest", cv_folds=3)
    space = {"n_estimators": [5, 10, 15, 20], "max_depth": [2, 3, 4]}

    result_a = search_hyperparameters(config, space, RandomSearch(n_iter=3, random_state=0), df=cv_df)
    result_b = search_hyperparameters(config, space, RandomSearch(n_iter=3, random_state=0), df=cv_df)

    assert [t.params for t in result_a.trials] == [t.params for t in result_b.trials]
    assert result_a.best_trial.score == result_b.best_trial.score
