"""Signature-based detection: a second, deterministic alert path
alongside the ML classifier (`nids.api.alerts.generate_alert`).

Rules are evaluated purely against the raw record (`FEATURE_COLUMNS`
values) -- never against a `PredictionResult` -- so a rule fires the same
way whether the classifier agrees, disagrees, or wasn't run at all. That
independence is structural, not incidental: nothing in this module
imports `nids.api.inference` or touches a served model.

Same "static data file, pure lookup, cached once" pattern
`nids.api.mitre` already uses for `mitre_attack_mapping.json` --
`detection_rules.yaml` here plays the same role. `Alert`'s shape doesn't
assume ML provenance (see `nids.api.alerts`): a rule match produces the
same dataclass, `source="rule"`, not a second alert type.
"""

from __future__ import annotations

import operator
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from nids.api.alerts import Alert, severity_rank
from nids.api.mitre import MitreMapping, MitreTechnique

_RULES_PATH = Path(__file__).parent / "detection_rules.yaml"

# Deterministic representative risk_score per severity -- a signature
# match has no confidence gradient the way a model prediction does (it
# either matched or it didn't), so there's no "score" to compute the way
# nids.api.risk.compute_risk_score does for the ML path. Same four-level
# vocabulary as nids.api.alerts._SEVERITY_ORDER, scaled 0-100.
_SEVERITY_SCORE = {"low": 10.0, "medium": 40.0, "high": 70.0, "critical": 100.0}

_OPERATORS = {
    "eq": operator.eq,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
}

_cached_rules: list[Rule] | None = None


@dataclass(frozen=True)
class RuleCondition:
    field: str
    operator: str
    value: Any


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    description: str
    severity: str
    conditions: list[RuleCondition]
    mitre: MitreMapping | None


def _entry_to_rule(entry: dict[str, Any]) -> Rule:
    mitre_entry = entry.get("mitre")
    mitre = (
        MitreMapping(
            tactic=mitre_entry["tactic"],
            techniques=[MitreTechnique(**t) for t in mitre_entry["techniques"]],
        )
        if mitre_entry is not None
        else None
    )
    return Rule(
        id=entry["id"],
        name=entry["name"],
        description=entry["description"],
        severity=entry["severity"],
        conditions=[RuleCondition(**c) for c in entry["conditions"]],
        mitre=mitre,
    )


def load_rules() -> list[Rule]:
    """Reads and caches `detection_rules.yaml` once for the process's
    lifetime -- same lazy-cache shape `nids.api.mitre.load_mitre_mapping`
    already uses, for the same reason (the file never changes
    mid-process, so re-parsing it per call would be pure waste)."""
    global _cached_rules
    if _cached_rules is None:
        data = yaml.safe_load(_RULES_PATH.read_text())
        _cached_rules = [_entry_to_rule(entry) for entry in data["rules"]]
    return _cached_rules


def _condition_matches(condition: RuleCondition, record: dict[str, Any]) -> bool:
    if condition.field not in record:
        return False
    try:
        return _OPERATORS[condition.operator](record[condition.field], condition.value)
    except TypeError:
        # e.g. a numeric operator (gt/lt/...) against a value that can't
        # be compared to condition.value -- a malformed rule/record
        # combination, not a match. Evaluation must never crash over one
        # bad rule; see evaluate_rules's docstring.
        return False


def _rule_matches(rule: Rule, record: dict[str, Any]) -> bool:
    """AND-combined: every condition must match. An empty conditions
    list would trivially match everything, which is never a realistic
    rule, but `all([])` being `True` is Python's own behavior, not
    special-cased here."""
    return all(_condition_matches(c, record) for c in rule.conditions)


def evaluate_rules(record: dict[str, Any], rules: list[Rule] | None = None) -> Rule | None:
    """The one entry point a caller (`nids.api.pipeline.finish_record`)
    needs: `None` if nothing matched, else the single highest-severity
    matching `Rule` (ties broken by declaration order in
    `detection_rules.yaml`, via `max`'s left-to-right stability) --
    deterministic regardless of how many rules happen to match.

    `rules` defaults to `load_rules()`; overridable for tests that don't
    want to depend on the shipped `detection_rules.yaml` contents.
    """
    candidates = rules if rules is not None else load_rules()
    matches = [r for r in candidates if _rule_matches(r, record)]
    if not matches:
        return None
    return max(matches, key=lambda r: severity_rank(r.severity))


def generate_rule_alert(rule: Rule) -> Alert:
    """Builds an `Alert` from a matched `Rule`. `attack_category` is
    `None` -- that's an ML-taxonomy concept (`PredictionResult.
    attack_category`, NSL-KDD's dos/probe/r2l/u2r) a signature match has
    no equivalent of; the rule's own `mitre` mapping (specified directly
    in `detection_rules.yaml`, not derived from an attack_category) is
    what carries technique context for a rule-sourced alert instead."""
    return Alert(
        alert_id=str(uuid.uuid4()),
        created_at=datetime.now(timezone.utc),
        level=rule.severity,
        title=rule.name,
        message=rule.description,
        risk_score=_SEVERITY_SCORE[rule.severity],
        attack_category=None,
        mitre=rule.mitre,
        source="rule",
    )
