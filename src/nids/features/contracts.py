"""The raw-record contract every input path must satisfy.

Batch CSV upload, PCAP-derived flow extraction, the live capture agent,
manual entry, and demo replay are all different ways of producing a
connection record. Each is responsible for mapping its native representation
onto this contract (a DataFrame with `FEATURE_COLUMNS` present and
numeric-coercible numeric columns); nothing downstream of this contract
should know or care which input path a record came from.
"""

from __future__ import annotations

import pandas as pd

from nids.data.schema import CATEGORICAL_COLUMNS, FEATURE_COLUMNS

NUMERIC_COLUMNS: list[str] = [c for c in FEATURE_COLUMNS if c not in CATEGORICAL_COLUMNS]


def validate_raw_records(df: pd.DataFrame) -> None:
    """Raise ValueError if `df` doesn't satisfy the raw-record contract.

    Checks structure only (required columns present, numeric columns are
    numeric-coercible) — it does not check categorical vocabulary, since
    novel category values (e.g. a service name never seen in training) are
    expected from live traffic and are handled downstream by the feature
    pipeline's encoders, not rejected here.
    """
    missing = [c for c in FEATURE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"Input is missing required raw feature column(s): {missing}. "
            "Every input adapter (batch CSV, PCAP flow extractor, live "
            "capture, manual entry, demo replay) must map its records onto "
            "nids.data.schema.FEATURE_COLUMNS before calling the feature "
            "pipeline."
        )

    non_numeric = [c for c in NUMERIC_COLUMNS if not _is_numeric_coercible(df[c])]
    if non_numeric:
        raise ValueError(
            f"Column(s) expected to be numeric are not numeric-coercible: {non_numeric}."
        )


def _is_numeric_coercible(series: pd.Series) -> bool:
    if pd.api.types.is_numeric_dtype(series):
        return True
    try:
        pd.to_numeric(series)
    except (ValueError, TypeError):
        return False
    return True
