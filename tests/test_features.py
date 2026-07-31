from pathlib import Path

import numpy as np
import pytest

from nids.data import loader
from nids.features import FeatureEngineer, FeatureMatrix
from nids.features.pipeline import FEATURE_SCHEMA_VERSION

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd.txt"


@pytest.fixture
def batch_df():
    return loader._read_nsl_kdd_file(FIXTURE)


def test_fit_transform_produces_dense_numeric_matrix(batch_df):
    fe = FeatureEngineer()
    matrix = fe.fit_transform(batch_df)

    assert isinstance(matrix, FeatureMatrix)
    assert matrix.X.shape[0] == len(batch_df)
    assert matrix.X.shape[1] == len(matrix.feature_names)
    assert np.isfinite(matrix.X).all()
    assert matrix.metadata["schema_version"] == FEATURE_SCHEMA_VERSION
    assert matrix.metadata["n_samples_fit"] == len(batch_df)
    assert matrix.metadata["n_samples_transformed"] == len(batch_df)


def test_transform_is_reusable_for_a_single_row_manual_entry(batch_df):
    """A single hand-entered record must flow through the exact same
    fitted pipeline as a batch, unchanged."""
    fe = FeatureEngineer().fit(batch_df)

    single_row = batch_df.iloc[[0]]
    matrix = fe.transform(single_row)

    assert matrix.X.shape == (1, len(fe.feature_names_out))
    assert matrix.feature_names == fe.feature_names_out


def test_transform_handles_unseen_categorical_values(batch_df):
    """Live-capture traffic will contain protocol/service/flag values never
    seen during training; the pipeline must not raise, unlike a naive encoder."""
    fe = FeatureEngineer().fit(batch_df)

    novel = batch_df.iloc[[0]].copy()
    novel["protocol_type"] = "icmp"  # fixture only contains "tcp"
    novel["service"] = "totally_novel_service"

    matrix = fe.transform(novel)
    assert matrix.X.shape == (1, len(fe.feature_names_out))
    assert np.isfinite(matrix.X).all()


def test_transform_rejects_records_missing_contract_columns(batch_df):
    fe = FeatureEngineer().fit(batch_df)
    broken = batch_df.drop(columns=["src_bytes"])

    with pytest.raises(ValueError, match="missing required raw feature column"):
        fe.transform(broken)


def test_transform_before_fit_raises(batch_df):
    fe = FeatureEngineer()
    with pytest.raises(RuntimeError, match="fit"):
        fe.transform(batch_df)


def test_fit_metadata_is_accessible_and_copied(batch_df):
    fe = FeatureEngineer().fit(batch_df)

    metadata = fe.fit_metadata
    assert metadata["schema_version"] == FEATURE_SCHEMA_VERSION
    assert metadata["n_samples_fit"] == len(batch_df)

    metadata["schema_version"] = "tampered"
    assert fe.fit_metadata["schema_version"] == FEATURE_SCHEMA_VERSION  # unaffected by mutation


def test_save_load_roundtrip_reproduces_identical_output(batch_df, tmp_path):
    fe = FeatureEngineer().fit(batch_df)
    original = fe.transform(batch_df)

    save_path = tmp_path / "feature_pipeline.joblib"
    fe.save(save_path)

    reloaded = FeatureEngineer.load(save_path)
    reproduced = reloaded.transform(batch_df)

    np.testing.assert_allclose(original.X, reproduced.X)
    assert original.feature_names == reproduced.feature_names
