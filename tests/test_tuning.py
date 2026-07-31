from pathlib import Path

import pytest
from mlflow.tracking import MlflowClient

from nids.data import loader
from nids.training import tuning as tuning_module
from nids.training.artifacts import load_cv_run
from nids.training.config import TrainingConfig
from nids.training.search import GridSearch, RandomSearch
from nids.training.tuning import TuningResult, run_hyperparameter_search, search_hyperparameters

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


def test_run_hyperparameter_search_saves_study_and_every_trial(cv_df, tmp_path):
    config = TrainingConfig(
        model_name="random_forest", cv_folds=3, artifact_root=tmp_path / "runs"
    )
    space = {"n_estimators": [5, 10]}

    tuning_run_artifacts = run_hyperparameter_search(
        config, space, GridSearch(), df=cv_df, log_to_mlflow=False
    )

    assert tuning_run_artifacts.run_dir.exists()
    assert len(tuning_run_artifacts.trials) == 2

    # every trial is independently loadable as a full CV run
    for trial_summary in tuning_run_artifacts.trials:
        trial_dir = (tmp_path / "runs") / trial_summary["run_id"]
        loaded = load_cv_run(trial_dir)
        assert loaded.n_folds == 3


def test_run_hyperparameter_search_best_trial_matches_pure_computation(cv_df, tmp_path):
    config = TrainingConfig(
        model_name="random_forest", cv_folds=3, artifact_root=tmp_path / "runs"
    )
    space = {"n_estimators": [5, 10, 15]}

    pure_result = search_hyperparameters(config, space, GridSearch(), df=cv_df)
    tuning_run_artifacts = run_hyperparameter_search(
        config, space, GridSearch(), df=cv_df, log_to_mlflow=False
    )

    assert tuning_run_artifacts.metadata["best_score"] == pytest.approx(pure_result.best_trial.score)
    assert tuning_run_artifacts.metadata["best_params"] == pure_result.best_trial.params


def test_run_hyperparameter_search_logs_parent_and_child_runs_to_mlflow(cv_df, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tracking_uri = f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}"

    config = TrainingConfig(
        model_name="random_forest",
        cv_folds=3,
        artifact_root=tmp_path / "runs",
        experiment_name="nids-tuning-test",
        tracking_uri=tracking_uri,
    )
    space = {"n_estimators": [5, 10]}

    run_hyperparameter_search(config, space, GridSearch(), df=cv_df)

    client = MlflowClient(tracking_uri=tracking_uri)
    experiment = client.get_experiment_by_name("nids-tuning-test")
    assert experiment is not None

    all_runs = client.search_runs([experiment.experiment_id])
    parent_runs = [r for r in all_runs if r.data.tags.get("run_type") == "hyperparameter_search"]
    child_runs = [r for r in all_runs if r.data.tags.get("run_type") == "cross_validation"]
    assert len(parent_runs) == 1
    assert len(child_runs) == 2
