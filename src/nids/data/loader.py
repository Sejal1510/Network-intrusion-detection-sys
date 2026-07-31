"""Load NSL-KDD CSV files into labeled, schema-typed DataFrames."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from nids.data.schema import ALL_COLUMNS, ATTACK_CATEGORY, CATEGORICAL_COLUMNS

RAW_DIR = Path("data/raw/nsl-kdd")


def _read_nsl_kdd_file(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python -m nids.data.download` first "
            "to fetch and verify the dataset."
        )

    df = pd.read_csv(path, names=ALL_COLUMNS, header=None)

    for col in CATEGORICAL_COLUMNS:
        df[col] = df[col].astype("category")

    unknown = set(df["attack_type"].unique()) - set(ATTACK_CATEGORY)
    if unknown:
        raise ValueError(
            f"Unrecognized attack_type value(s) in {path.name}: {sorted(unknown)}. "
            "Update ATTACK_CATEGORY in nids.data.schema."
        )

    df["attack_category"] = df["attack_type"].map(ATTACK_CATEGORY).astype("category")
    df["is_attack"] = (df["attack_category"] != "normal").astype(int)

    return df


def load_train(full: bool = True, raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """Load the training split.

    `full=False` loads the 20%-subsample (KDDTrain+_20Percent.txt), useful for
    quick local iteration; `full=True` loads the complete KDDTrain+.txt.
    """
    filename = "KDDTrain+.txt" if full else "KDDTrain+_20Percent.txt"
    return _read_nsl_kdd_file(raw_dir / filename)


def load_test(exclude_difficulty_21: bool = False, raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    """Load the test split.

    `exclude_difficulty_21=True` loads KDDTest-21.txt, which drops records the
    original KDD-99 classifiers scored perfectly on (difficulty level 21),
    yielding a harder evaluation set.
    """
    filename = "KDDTest-21.txt" if exclude_difficulty_21 else "KDDTest+.txt"
    return _read_nsl_kdd_file(raw_dir / filename)
