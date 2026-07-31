import pytest

from nids.training.search import GridSearch, RandomSearch


def test_grid_search_enumerates_full_cartesian_product():
    space = {"n_estimators": [10, 20], "max_depth": [3, 5, None]}

    candidates = GridSearch().generate_candidates(space)

    assert len(candidates) == 6
    assert {"n_estimators": 10, "max_depth": 3} in candidates
    assert {"n_estimators": 20, "max_depth": None} in candidates
    # no duplicates
    assert len({tuple(sorted(c.items(), key=str)) for c in candidates}) == 6


def test_grid_search_empty_space_yields_single_empty_candidate():
    assert GridSearch().generate_candidates({}) == [{}]


def test_grid_search_is_deterministic_across_calls():
    space = {"a": [1, 2, 3], "b": ["x", "y"]}

    first = GridSearch().generate_candidates(space)
    second = GridSearch().generate_candidates(space)

    assert first == second


def test_grid_search_single_key_single_value():
    assert GridSearch().generate_candidates({"a": [1]}) == [{"a": 1}]


def test_random_search_respects_n_iter():
    space = {"n_estimators": [10, 20, 30], "max_depth": [3, 5, 7]}

    candidates = RandomSearch(n_iter=4, random_state=0).generate_candidates(space)

    assert len(candidates) == 4


def test_random_search_caps_at_full_grid_size_without_duplicates():
    space = {"a": [1, 2], "b": ["x", "y"]}  # 4 total combinations

    candidates = RandomSearch(n_iter=100, random_state=0).generate_candidates(space)

    assert len(candidates) == 4
    unique = {tuple(sorted(c.items(), key=str)) for c in candidates}
    assert len(unique) == 4  # no duplicate picks


def test_random_search_is_deterministic_given_same_seed():
    space = {"n_estimators": [10, 20, 30, 40], "max_depth": [3, 5, 7]}

    first = RandomSearch(n_iter=3, random_state=42).generate_candidates(space)
    second = RandomSearch(n_iter=3, random_state=42).generate_candidates(space)

    assert first == second


def test_random_search_different_seeds_can_differ():
    space = {"n_estimators": [10, 20, 30, 40, 50, 60], "max_depth": [3, 5, 7, 9]}

    first = RandomSearch(n_iter=3, random_state=1).generate_candidates(space)
    second = RandomSearch(n_iter=3, random_state=2).generate_candidates(space)

    assert first != second


def test_random_search_rejects_non_positive_n_iter():
    with pytest.raises(ValueError, match="n_iter"):
        RandomSearch(n_iter=0)
