"""Training run configuration: every knob that affects a training run's
output lives here, so a run's config is exactly what needs to be persisted
(see nids.training.artifacts) to reproduce it later.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

VALID_LABEL_COLUMNS = frozenset({"is_attack", "attack_category"})


@dataclasses.dataclass(frozen=True)
class TrainingConfig:
    model_name: str = "catboost"
    model_params: dict[str, Any] = dataclasses.field(default_factory=dict)
    random_seed: int = 42

    # Dataset selection (see nids.data.loader)
    train_full: bool = True
    test_exclude_difficulty_21: bool = False
    label_column: str = "is_attack"

    # Experiment tracking / artifact naming (see nids.training.artifacts,
    # nids.training.tracking)
    experiment_name: str = "nids-baseline"
    run_name: str | None = None
    artifact_root: Path = Path("models/runs")
    tracking_uri: str = "sqlite:///mlflow.db"

    def __post_init__(self) -> None:
        if self.label_column not in VALID_LABEL_COLUMNS:
            raise ValueError(
                f"label_column must be one of {sorted(VALID_LABEL_COLUMNS)}, "
                f"got {self.label_column!r}."
            )

    def to_dict(self) -> dict[str, Any]:
        """A JSON-serializable representation, for persisting alongside a
        run's other artifacts."""
        data = dataclasses.asdict(self)
        data["artifact_root"] = str(self.artifact_root)
        return data
