import pytest

from nids.api import mitre as mitre_module
from nids.api.mitre import MitreMapping, load_mitre_mapping, map_to_mitre
from nids.data.schema import ATTACK_CATEGORY


def test_map_to_mitre_returns_none_for_none_attack_category():
    """is_attack-only deployments: PredictionResult.attack_category is
    None, and that must not be treated as an unmapped category error."""
    assert map_to_mitre(None) is None


def test_map_to_mitre_returns_none_for_normal():
    assert map_to_mitre("normal") is None


def test_map_to_mitre_returns_none_for_unknown_category():
    assert map_to_mitre("not_a_real_category") is None


@pytest.mark.parametrize("category", ["dos", "probe", "r2l", "u2r"])
def test_map_to_mitre_maps_every_non_normal_category(category):
    mapping = map_to_mitre(category)

    assert isinstance(mapping, MitreMapping)
    assert mapping.tactic
    assert len(mapping.techniques) > 0
    for technique in mapping.techniques:
        assert technique.id.startswith("T")
        assert technique.name
        assert technique.url.startswith("https://attack.mitre.org/")


def test_every_attack_category_taxonomy_value_is_handled():
    """Every category nids.data.schema.ATTACK_CATEGORY can ever produce
    either maps to a real MitreMapping or is the documented "normal"
    no-mapping case -- nothing silently falls through."""
    for category in set(ATTACK_CATEGORY.values()):
        mapping = map_to_mitre(category)
        if category == "normal":
            assert mapping is None
        else:
            assert mapping is not None


def test_mapping_is_cached_after_first_load(monkeypatch):
    mitre_module._cached_mapping = None
    real_contents = mitre_module._MAPPING_PATH.read_text()
    read_calls = {"n": 0}

    class _CountingPath:
        def read_text(self) -> str:
            read_calls["n"] += 1
            return real_contents

    monkeypatch.setattr(mitre_module, "_MAPPING_PATH", _CountingPath())

    load_mitre_mapping()
    load_mitre_mapping()

    assert read_calls["n"] == 1
