from pathlib import Path

import pytest

from nids.data import download, loader
from nids.data.schema import ALL_COLUMNS, ATTACK_CATEGORY, FEATURE_COLUMNS

FIXTURE = Path(__file__).parent / "fixtures" / "sample_kdd.txt"


def test_schema_shape():
    assert len(FEATURE_COLUMNS) == 41
    assert ALL_COLUMNS == [*FEATURE_COLUMNS, "attack_type", "difficulty"]


def test_attack_category_taxonomy_is_closed():
    assert set(ATTACK_CATEGORY.values()) == {"normal", "dos", "probe", "r2l", "u2r"}
    assert ATTACK_CATEGORY["normal"] == "normal"


def test_loader_parses_fixture_and_derives_labels():
    df = loader._read_nsl_kdd_file(FIXTURE)

    assert len(df) == 4
    assert list(df.columns) == [*ALL_COLUMNS, "attack_category", "is_attack"]
    assert df["protocol_type"].dtype.name == "category"

    assert df.loc[0, "attack_type"] == "normal"
    assert df.loc[0, "is_attack"] == 0
    assert df.loc[0, "attack_category"] == "normal"

    assert df.loc[1, "attack_type"] == "neptune"
    assert df.loc[1, "is_attack"] == 1
    assert df.loc[1, "attack_category"] == "dos"

    assert df.loc[2, "attack_category"] == "probe"
    assert df.loc[3, "attack_category"] == "r2l"


def test_loader_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        loader._read_nsl_kdd_file(tmp_path / "does-not-exist.txt")


def test_loader_unknown_attack_type_raises(tmp_path):
    bad_file = tmp_path / "bad.txt"
    bad_row = FIXTURE.read_text().splitlines()[0].rsplit(",", 2)
    bad_row = ",".join([bad_row[0], "totally_unknown_attack", bad_row[2]])
    bad_file.write_text(bad_row + "\n")

    with pytest.raises(ValueError, match="Unrecognized attack_type"):
        loader._read_nsl_kdd_file(bad_file)


def test_download_verifies_checksum_and_rejects_mismatch(tmp_path, monkeypatch):
    monkeypatch.setattr(download, "FILES", {"fake.txt": "0" * 64})

    class FakeResponse:
        content = b"not the expected bytes"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(download.requests, "get", lambda *a, **k: FakeResponse())

    with pytest.raises(RuntimeError, match="Checksum mismatch"):
        download.fetch_dataset(dest=tmp_path)

    assert not (tmp_path / "fake.txt").exists()


def test_download_skips_already_verified_file(tmp_path, monkeypatch):
    import hashlib

    content = b"hello world"
    sha = hashlib.sha256(content).hexdigest()
    monkeypatch.setattr(download, "FILES", {"fake.txt": sha})
    (tmp_path / "fake.txt").write_bytes(content)

    def fail_if_called(*a, **k):
        raise AssertionError("should not re-download an already-verified file")

    monkeypatch.setattr(download.requests, "get", fail_if_called)

    download.fetch_dataset(dest=tmp_path)
