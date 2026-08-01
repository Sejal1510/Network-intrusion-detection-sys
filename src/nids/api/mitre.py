"""MITRE ATT&CK mapping: a static, data-driven lookup from
`nids.data.schema.ATTACK_CATEGORY` categories to MITRE tactics/techniques.

Deliberately data, not code: `mitre_attack_mapping.json` (next to this
module) is the entire mapping. Adding techniques, remapping a category, or
swapping in a different taxonomy for a different dataset is a JSON edit,
never a change to `map_to_mitre` itself.

Mapping precision is capped at `attack_category` granularity (dos, probe,
r2l, u2r) -- NSL-KDD's finer `attack_type` (e.g. "neptune", "satan") isn't
exposed past training (see `nids.api.inference`), so it isn't available to
map against here. `is_attack`-only deployments have no `attack_category`
at all (`PredictionResult.attack_category is None`), so they get no MITRE
mapping -- an honest `None`, not a guess.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_MAPPING_PATH = Path(__file__).parent / "mitre_attack_mapping.json"

_cached_mapping: dict[str, Any] | None = None


@dataclass(frozen=True)
class MitreTechnique:
    id: str
    name: str
    url: str


@dataclass(frozen=True)
class MitreMapping:
    tactic: str
    techniques: list[MitreTechnique]


def load_mitre_mapping() -> dict[str, Any]:
    """Reads and caches `mitre_attack_mapping.json` once for the
    process's lifetime -- same lazy-cache shape `nids.api.explain`'s
    explainer cache already uses, for the same reason (the data never
    changes mid-process, so re-reading it per call would be pure waste)."""
    global _cached_mapping
    if _cached_mapping is None:
        _cached_mapping = json.loads(_MAPPING_PATH.read_text())
    return _cached_mapping


def map_to_mitre(attack_category: str | None) -> MitreMapping | None:
    """Look up a MITRE mapping for an `attack_category` value.

    Returns `None` for `"normal"`, for `None` (is_attack-only
    deployments), or for any category absent from the mapping file (e.g.
    a future category the table hasn't been updated for) -- every case
    where guessing would be worse than admitting there's no mapping.
    """
    if attack_category is None:
        return None

    entry = load_mitre_mapping().get(attack_category)
    if entry is None:
        return None

    return MitreMapping(
        tactic=entry["tactic"],
        techniques=[MitreTechnique(**technique) for technique in entry["techniques"]],
    )
