"""Dataset acquisition and loading for the NIDS platform."""

from nids.data.loader import load_test, load_train
from nids.data.schema import ATTACK_CATEGORY, FEATURE_COLUMNS, LABEL_COLUMN

__all__ = [
    "ATTACK_CATEGORY",
    "FEATURE_COLUMNS",
    "LABEL_COLUMN",
    "load_test",
    "load_train",
]
