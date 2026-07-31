"""Model-agnostic feature engineering — the single source of truth used by
every prediction path (batch CSV, PCAP flow, live capture, manual entry,
demo replay) and every model (CatBoost, Random Forest, LightGBM, XGBoost, ...).
"""

from nids.features.contracts import validate_raw_records
from nids.features.pipeline import FeatureEngineer, FeatureMatrix

__all__ = ["FeatureEngineer", "FeatureMatrix", "validate_raw_records"]
