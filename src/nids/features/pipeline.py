"""Model-agnostic feature engineering: the single source of truth for turning
a raw connection record (from any input path) into a model-ready feature
matrix.

This module's responsibility ends at producing a validated, reproducible
`FeatureMatrix`. It has no knowledge of any specific model (CatBoost, Random
Forest, LightGBM, XGBoost, ...) and no knowledge of labels — a training
pipeline consumes its output and pairs it with whatever label column it
needs; this module never reads `attack_type` / `is_attack` / `attack_category`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from nids.data.schema import CATEGORICAL_COLUMNS, FEATURE_COLUMNS
from nids.features.contracts import NUMERIC_COLUMNS, validate_raw_records

# Bump this whenever the raw contract or the encoding scheme changes in a way
# that makes an old fitted pipeline invalid for new data (or vice versa).
FEATURE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class FeatureMatrix:
    """Model-agnostic output: a plain numeric matrix plus enough metadata to
    audit and reproduce it. No model ever receives anything but this shape.
    """

    X: np.ndarray
    feature_names: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


def _build_column_transformer() -> ColumnTransformer:
    numeric_pipeline = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("encode", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    return ColumnTransformer(
        transformers=[
            ("numeric", numeric_pipeline, NUMERIC_COLUMNS),
            ("categorical", categorical_pipeline, CATEGORICAL_COLUMNS),
        ]
    )


class FeatureEngineer:
    """Fit once on training data, reuse unchanged for every input path.

    Usage:
        fe = FeatureEngineer().fit(train_df)
        train_matrix = fe.transform(train_df)
        fe.save("models/feature_pipeline.joblib")

        # later, in any consumption path (batch CSV, live capture, manual
        # entry, demo replay, ...), after that path's adapter has produced a
        # DataFrame satisfying the raw-record contract:
        fe = FeatureEngineer.load("models/feature_pipeline.joblib")
        matrix = fe.transform(new_df)
    """

    def __init__(self) -> None:
        self._column_transformer: ColumnTransformer | None = None
        self._fit_metadata: dict[str, Any] = {}

    @property
    def is_fitted(self) -> bool:
        return self._column_transformer is not None

    @property
    def feature_names_out(self) -> list[str]:
        if not self.is_fitted:
            raise RuntimeError("FeatureEngineer is not fitted yet.")
        return list(self._column_transformer.get_feature_names_out())

    @property
    def fit_metadata(self) -> dict[str, Any]:
        """Schema version, library version, fit timestamp, etc. recorded at
        fit time -- for callers (e.g. artifact persistence) that need it
        without reaching into a private attribute."""
        return dict(self._fit_metadata)

    def fit(self, df: pd.DataFrame) -> FeatureEngineer:
        validate_raw_records(df)

        self._column_transformer = _build_column_transformer()
        self._column_transformer.fit(df[FEATURE_COLUMNS])

        self._fit_metadata = {
            "schema_version": FEATURE_SCHEMA_VERSION,
            "sklearn_version": sklearn.__version__,
            "fitted_at": datetime.now(timezone.utc).isoformat(),
            "n_samples_fit": len(df),
            "feature_names_out": self.feature_names_out,
        }
        return self

    def transform(self, df: pd.DataFrame) -> FeatureMatrix:
        if not self.is_fitted:
            raise RuntimeError("FeatureEngineer.fit(...) must be called before transform(...).")
        validate_raw_records(df)

        X = self._column_transformer.transform(df[FEATURE_COLUMNS])
        metadata = {**self._fit_metadata, "n_samples_transformed": len(df)}
        return FeatureMatrix(X=X, feature_names=self.feature_names_out, metadata=metadata)

    def fit_transform(self, df: pd.DataFrame) -> FeatureMatrix:
        return self.fit(df).transform(df)

    def save(self, path: str | Path) -> None:
        if not self.is_fitted:
            raise RuntimeError("Cannot save an unfitted FeatureEngineer.")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {"column_transformer": self._column_transformer, "fit_metadata": self._fit_metadata},
            path,
        )

    @classmethod
    def load(cls, path: str | Path) -> FeatureEngineer:
        payload = joblib.load(Path(path))
        fe = cls()
        fe._column_transformer = payload["column_transformer"]
        fe._fit_metadata = payload["fit_metadata"]
        return fe
