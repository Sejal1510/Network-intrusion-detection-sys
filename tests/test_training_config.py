import dataclasses
import json
from pathlib import Path

import pytest

from nids.training.config import TrainingConfig


def test_defaults():
    config = TrainingConfig()
    assert config.model_name == "catboost"
    assert config.random_seed == 42
    assert config.label_column == "is_attack"
    assert config.artifact_root == Path("models/runs")
    assert config.cv_folds == 5


def test_is_frozen():
    config = TrainingConfig()
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.model_name = "random_forest"


def test_model_params_default_is_not_shared_between_instances():
    a = TrainingConfig()
    b = TrainingConfig()
    a.model_params["depth"] = 4
    assert "depth" not in b.model_params


def test_rejects_unknown_label_column():
    with pytest.raises(ValueError, match="label_column"):
        TrainingConfig(label_column="not_a_real_column")


def test_rejects_cv_folds_below_two():
    with pytest.raises(ValueError, match="cv_folds"):
        TrainingConfig(cv_folds=1)


def test_to_dict_is_json_serializable():
    config = TrainingConfig(model_params={"iterations": 50}, artifact_root=Path("models/runs"))
    payload = config.to_dict()

    serialized = json.dumps(payload)  # must not raise
    reloaded = json.loads(serialized)

    assert reloaded["model_name"] == "catboost"
    assert reloaded["artifact_root"] == str(Path("models/runs"))
    assert reloaded["model_params"] == {"iterations": 50}
