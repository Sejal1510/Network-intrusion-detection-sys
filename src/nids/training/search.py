"""Search strategies for hyperparameter tuning, decoupled from the training/
evaluation logic that scores each candidate (see nids.training.tuning).

A strategy's only job is turning a search space into a list of candidate
hyperparameter dicts to try -- it never touches data, models, or metrics.
Adding a new strategy (e.g. Bayesian optimization) means writing a new
class satisfying `SearchStrategy`; nothing in nids.training.tuning changes.
"""

from __future__ import annotations

import itertools
from typing import Any, Protocol

import numpy as np


class SearchStrategy(Protocol):
    def generate_candidates(self, search_space: dict[str, list[Any]]) -> list[dict[str, Any]]:
        """Return every hyperparameter combination to try, as a list of
        {param_name: value} dicts to merge into TrainingConfig.model_params."""
        ...


class GridSearch:
    """Exhaustively enumerate every combination in the search space, in a
    fixed, deterministic order -- no randomness involved."""

    def generate_candidates(self, search_space: dict[str, list[Any]]) -> list[dict[str, Any]]:
        if not search_space:
            return [{}]
        keys = sorted(search_space)
        value_combinations = itertools.product(*(search_space[key] for key in keys))
        return [dict(zip(keys, values, strict=True)) for values in value_combinations]


class RandomSearch:
    """Sample `n_iter` combinations from the search space's full grid
    uniformly at random, without replacement (capped at the grid's size),
    using a fixed seed for reproducibility."""

    def __init__(self, n_iter: int, random_state: int = 42):
        if n_iter < 1:
            raise ValueError(f"n_iter must be >= 1, got {n_iter}.")
        self.n_iter = n_iter
        self.random_state = random_state

    def generate_candidates(self, search_space: dict[str, list[Any]]) -> list[dict[str, Any]]:
        full_grid = GridSearch().generate_candidates(search_space)
        rng = np.random.RandomState(self.random_state)
        n = min(self.n_iter, len(full_grid))
        chosen_idx = rng.choice(len(full_grid), size=n, replace=False)
        return [full_grid[i] for i in chosen_idx]
