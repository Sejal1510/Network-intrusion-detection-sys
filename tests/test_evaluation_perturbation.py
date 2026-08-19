import numpy as np
import pandas as pd
import pytest

from nids.data.schema import FEATURE_COLUMNS
from nids.evaluation.perturbation import (
    ALL_ALLOWED_FEATURES,
    TIER1_FEATURES,
    TIER2_FEATURES,
    TIER3_FEATURES,
    FeatureBounds,
    perturbation_deltas,
    repair,
    sample_perturbation,
)

EXCLUDED_FEATURES = {
    "protocol_type",
    "service",
    "flag",
    "land",
    "logged_in",
    "root_shell",
    "su_attempted",
    "is_host_login",
    "is_guest_login",
    "num_compromised",
    "num_outbound_cmds",
    "dst_bytes",
}


def test_tiers_are_disjoint_and_cover_the_allowlist():
    tier1, tier2, tier3 = set(TIER1_FEATURES), set(TIER2_FEATURES), set(TIER3_FEATURES)
    assert not (tier1 & tier2)
    assert not (tier1 & tier3)
    assert not (tier2 & tier3)
    assert set(ALL_ALLOWED_FEATURES) == tier1 | tier2 | tier3


def test_allowlist_plus_excluded_covers_every_feature_column():
    assert set(ALL_ALLOWED_FEATURES) | EXCLUDED_FEATURES == set(FEATURE_COLUMNS)
    assert not (set(ALL_ALLOWED_FEATURES) & EXCLUDED_FEATURES)


@pytest.fixture
def sample_row() -> pd.Series:
    return pd.Series(
        {
            "duration": 10.0,
            "protocol_type": "tcp",
            "service": "http",
            "flag": "SF",
            "src_bytes": 500.0,
            "dst_bytes": 300.0,
            "land": 0,
            "wrong_fragment": 0,
            "urgent": 0,
            "hot": 4,
            "num_failed_logins": 2,
            "logged_in": 1,
            "num_compromised": 0,
            "root_shell": 0,
            "su_attempted": 0,
            "num_root": 3,
            "num_file_creations": 5,
            "num_shells": 1,
            "num_access_files": 2,
            "num_outbound_cmds": 0,
            "is_host_login": 0,
            "is_guest_login": 0,
            "count": 20,
            "srv_count": 15,
            "serror_rate": 0.4,
            "srv_serror_rate": 0.4,
            "rerror_rate": 0.3,
            "srv_rerror_rate": 0.3,
            "same_srv_rate": 0.5,
            "diff_srv_rate": 0.4,
            "srv_diff_host_rate": 0.1,
            "dst_host_count": 100,
            "dst_host_srv_count": 80,
            "dst_host_same_srv_rate": 0.6,
            "dst_host_diff_srv_rate": 0.5,
            "dst_host_same_src_port_rate": 0.2,
            "dst_host_srv_diff_host_rate": 0.1,
            "dst_host_serror_rate": 0.5,
            "dst_host_srv_serror_rate": 0.4,
            "dst_host_rerror_rate": 0.4,
            "dst_host_srv_rerror_rate": 0.3,
        }
    )


@pytest.fixture
def train_df(sample_row) -> pd.DataFrame:
    low = sample_row.copy()
    for feature in TIER1_FEATURES:
        low[feature] = 0
    high = sample_row.copy()
    for feature in TIER1_FEATURES:
        high[feature] = 1000
    return pd.DataFrame([low, sample_row, high])


def test_feature_bounds_from_train_df_only_covers_tier1(train_df):
    bounds = FeatureBounds.from_train_df(train_df, upper_quantile=1.0)

    assert set(bounds.tier1_bounds) == set(TIER1_FEATURES)
    for feature in TIER1_FEATURES:
        assert bounds.tier1_bounds[feature] == (0.0, 1000.0)


def test_feature_bounds_upper_quantile_is_robust_to_outliers():
    # 9999 ordinary rows clustered near 100, one extreme outlier at 10 million
    # (mirrors NSL-KDD's real src_bytes: training max ~1.38e9 vs. a 99.9th
    # percentile of ~2.2e6) -- the bound must track the bulk, not the outlier.
    values = [100.0] * 9999 + [10_000_000.0]
    train_df = pd.DataFrame({feature: values for feature in TIER1_FEATURES})

    bounds = FeatureBounds.from_train_df(train_df, upper_quantile=0.999)

    for feature in TIER1_FEATURES:
        _, hi = bounds.tier1_bounds[feature]
        assert hi < 10_000_000.0
        assert hi < 1000.0  # nowhere near the outlier


def test_sample_perturbation_never_touches_excluded_features(sample_row, train_df):
    bounds = FeatureBounds.from_train_df(train_df)
    rng = np.random.default_rng(0)

    candidate = sample_perturbation(sample_row, bounds, epsilon=0.3, rng=rng)

    for feature in EXCLUDED_FEATURES:
        assert candidate[feature] == sample_row[feature]


def test_sample_perturbation_respects_bounds_over_many_trials(sample_row, train_df):
    bounds = FeatureBounds.from_train_df(train_df)
    rng = np.random.default_rng(0)

    for _ in range(200):
        candidate = sample_perturbation(sample_row, bounds, epsilon=0.3, rng=rng)

        for feature in TIER1_FEATURES:
            lo, hi = bounds.tier1_bounds[feature]
            assert lo - 1e-9 <= candidate[feature] <= hi + 1e-9
        for feature in TIER2_FEATURES:
            assert -1e-9 <= candidate[feature] <= 1 + 1e-9
        for feature in TIER3_FEATURES:
            assert 0 <= candidate[feature] <= sample_row[feature] + 1e-9  # decrease-only


def test_sample_perturbation_keeps_integer_features_integer(sample_row, train_df):
    bounds = FeatureBounds.from_train_df(train_df)
    rng = np.random.default_rng(0)

    candidate = sample_perturbation(sample_row, bounds, epsilon=0.3, rng=rng)

    for feature in TIER1_FEATURES + TIER3_FEATURES:
        assert float(candidate[feature]).is_integer()


def test_repair_clips_srv_count_to_count():
    row = pd.Series({"count": 5, "srv_count": 20, "dst_host_count": 0, "dst_host_srv_count": 0})
    for a, b in [("same_srv_rate", "diff_srv_rate"), ("serror_rate", "rerror_rate"),
                 ("srv_serror_rate", "srv_rerror_rate"), ("dst_host_same_srv_rate", "dst_host_diff_srv_rate"),
                 ("dst_host_serror_rate", "dst_host_rerror_rate"),
                 ("dst_host_srv_serror_rate", "dst_host_srv_rerror_rate")]:
        row[a] = 0.0
        row[b] = 0.0

    repaired = repair(row)

    assert repaired["srv_count"] == 5


def test_repair_rescales_rate_pairs_summing_over_one():
    row = pd.Series(
        {
            "count": 0,
            "srv_count": 0,
            "dst_host_count": 0,
            "dst_host_srv_count": 0,
            "same_srv_rate": 0.8,
            "diff_srv_rate": 0.8,
            "serror_rate": 0.0,
            "rerror_rate": 0.0,
            "srv_serror_rate": 0.0,
            "srv_rerror_rate": 0.0,
            "dst_host_same_srv_rate": 0.0,
            "dst_host_diff_srv_rate": 0.0,
            "dst_host_serror_rate": 0.0,
            "dst_host_rerror_rate": 0.0,
            "dst_host_srv_serror_rate": 0.0,
            "dst_host_srv_rerror_rate": 0.0,
        }
    )

    repaired = repair(row)

    assert repaired["same_srv_rate"] + repaired["diff_srv_rate"] == pytest.approx(1.0)
    assert repaired["same_srv_rate"] == pytest.approx(0.5)
    assert repaired["diff_srv_rate"] == pytest.approx(0.5)


def test_perturbation_deltas_reports_only_nonzero_allowlisted_changes(sample_row):
    perturbed = sample_row.copy()
    perturbed["duration"] = sample_row["duration"] + 5
    perturbed["service"] = "ftp"  # not allowlisted -- must never appear

    deltas = perturbation_deltas(sample_row, perturbed)

    assert deltas == {"duration": 5.0}
