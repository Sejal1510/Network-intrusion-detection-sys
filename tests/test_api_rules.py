from nids.api.alerts import Alert
from nids.api.mitre import MitreMapping, MitreTechnique
from nids.api.rules import (
    Rule,
    RuleCondition,
    evaluate_rules,
    generate_rule_alert,
    load_rules,
)


def _rule(
    rule_id="TEST-1",
    severity="high",
    conditions=None,
    mitre=None,
) -> Rule:
    if conditions is None:
        conditions = [RuleCondition(field="flag", operator="eq", value="S0")]
    return Rule(
        id=rule_id,
        name=f"Test rule {rule_id}",
        description="A rule built for a test.",
        severity=severity,
        conditions=list(conditions),
        mitre=mitre,
    )


# --- load_rules (the shipped detection_rules.yaml) --------------------------


def test_load_rules_returns_the_shipped_starter_rules():
    rules = load_rules()

    assert len(rules) >= 4
    ids = [r.id for r in rules]
    assert len(ids) == len(set(ids)), "rule ids must be unique"
    for rule in rules:
        assert rule.severity in {"low", "medium", "high", "critical"}
        assert len(rule.conditions) >= 1


def test_load_rules_is_cached_across_calls():
    assert load_rules() is load_rules()


# --- evaluate_rules: operators ------------------------------------------------


def test_evaluate_rules_eq_operator_matches():
    rule = _rule(conditions=[RuleCondition(field="flag", operator="eq", value="S0")])
    assert evaluate_rules({"flag": "S0"}, rules=[rule]) is rule
    assert evaluate_rules({"flag": "SF"}, rules=[rule]) is None


def test_evaluate_rules_gt_operator_matches():
    rule = _rule(conditions=[RuleCondition(field="count", operator="gt", value=100)])
    assert evaluate_rules({"count": 101}, rules=[rule]) is rule
    assert evaluate_rules({"count": 100}, rules=[rule]) is None


def test_evaluate_rules_gte_operator_matches():
    rule = _rule(conditions=[RuleCondition(field="num_failed_logins", operator="gte", value=3)])
    assert evaluate_rules({"num_failed_logins": 3}, rules=[rule]) is rule
    assert evaluate_rules({"num_failed_logins": 2}, rules=[rule]) is None


def test_evaluate_rules_lt_operator_matches():
    rule = _rule(conditions=[RuleCondition(field="duration", operator="lt", value=5)])
    assert evaluate_rules({"duration": 4}, rules=[rule]) is rule
    assert evaluate_rules({"duration": 5}, rules=[rule]) is None


def test_evaluate_rules_lte_operator_matches():
    rule = _rule(conditions=[RuleCondition(field="duration", operator="lte", value=5)])
    assert evaluate_rules({"duration": 5}, rules=[rule]) is rule
    assert evaluate_rules({"duration": 6}, rules=[rule]) is None


# --- evaluate_rules: AND-combination, missing fields, malformed data --------


def test_evaluate_rules_requires_every_condition_to_match():
    rule = _rule(
        conditions=[
            RuleCondition(field="is_guest_login", operator="eq", value=1),
            RuleCondition(field="logged_in", operator="eq", value=1),
        ]
    )
    assert evaluate_rules({"is_guest_login": 1, "logged_in": 0}, rules=[rule]) is None
    assert evaluate_rules({"is_guest_login": 1, "logged_in": 1}, rules=[rule]) is rule


def test_evaluate_rules_missing_field_is_not_a_match_not_a_crash():
    rule = _rule(conditions=[RuleCondition(field="does_not_exist", operator="eq", value=1)])
    assert evaluate_rules({"flag": "S0"}, rules=[rule]) is None


def test_evaluate_rules_type_mismatch_is_not_a_match_not_a_crash():
    # A numeric operator against a non-numeric value must not raise.
    rule = _rule(conditions=[RuleCondition(field="flag", operator="gt", value=100)])
    assert evaluate_rules({"flag": "S0"}, rules=[rule]) is None


def test_evaluate_rules_returns_none_when_no_rules_match():
    rule = _rule(conditions=[RuleCondition(field="flag", operator="eq", value="S0")])
    assert evaluate_rules({"flag": "SF"}, rules=[rule]) is None


def test_evaluate_rules_empty_rule_list_returns_none():
    assert evaluate_rules({"flag": "S0"}, rules=[]) is None


# --- evaluate_rules: multiple matches, severity ranking ----------------------


def test_evaluate_rules_picks_the_highest_severity_match():
    low = _rule(rule_id="LOW", severity="low", conditions=[RuleCondition("flag", "eq", "S0")])
    critical = _rule(
        rule_id="CRIT", severity="critical", conditions=[RuleCondition("count", "gt", 0)]
    )
    record = {"flag": "S0", "count": 1}

    assert evaluate_rules(record, rules=[low, critical]) is critical
    # Order in the candidate list must not matter.
    assert evaluate_rules(record, rules=[critical, low]) is critical


def test_evaluate_rules_ties_broken_by_declaration_order():
    first = _rule(rule_id="FIRST", severity="high", conditions=[RuleCondition("flag", "eq", "S0")])
    second = _rule(rule_id="SECOND", severity="high", conditions=[RuleCondition("count", "gt", 0)])
    record = {"flag": "S0", "count": 1}

    assert evaluate_rules(record, rules=[first, second]) is first


# --- generate_rule_alert ------------------------------------------------------


def test_generate_rule_alert_shape():
    mapping = MitreMapping(
        tactic="Impact",
        techniques=[MitreTechnique(id="T1498", name="Network DoS", url="https://example.com")],
    )
    rule = _rule(rule_id="R001", severity="critical", mitre=mapping)

    alert = generate_rule_alert(rule)

    assert isinstance(alert, Alert)
    assert alert.source == "rule"
    assert alert.level == "critical"
    assert alert.title == rule.name
    assert alert.message == rule.description
    assert alert.mitre is mapping
    assert alert.attack_category is None
    assert 0.0 <= alert.risk_score <= 100.0


def test_generate_rule_alert_risk_score_increases_with_severity():
    scores = {
        severity: generate_rule_alert(_rule(severity=severity)).risk_score
        for severity in ("low", "medium", "high", "critical")
    }
    assert scores["low"] < scores["medium"] < scores["high"] < scores["critical"]


def test_generate_rule_alert_has_a_unique_id_each_time():
    rule = _rule()
    assert generate_rule_alert(rule).alert_id != generate_rule_alert(rule).alert_id


def test_generate_rule_alert_without_mitre():
    alert = generate_rule_alert(_rule(mitre=None))
    assert alert.mitre is None
