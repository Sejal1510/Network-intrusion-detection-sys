# Rule-Based Detections: Signature Matching Alongside the ML Classifier

**Status: Milestone 13.** Closes the last named-but-unbuilt item in
`docs/API.md`'s "Future endpoints" (present since Milestone 5): a second,
deterministic detection path alongside the ML classifier
(`nids.api.alerts.generate_alert`). Chosen over threat-intel enrichment
(the remaining alternative) because it carries zero external-dependency
fragility (fully offline, no API key, no live-demo risk) while adding a
genuinely new detection *mechanism* rather than an enrichment layer on
top of an existing one — real NIDS platforms (Snort, Suricata, Zeek) are
hybrid ML+signature systems, not ML-only, and this closes exactly that
gap. `nids.api.alerts.Alert` was already documented as not assuming ML
provenance (`source="rule"`) since the note was written in Milestone 5's
own forward-looking docs — this milestone is that plan, built.

## Independence from the ML path

The one property everything else depends on: **a rule is evaluated
purely against the raw record** (`nids.data.schema.FEATURE_COLUMNS`
values) **— never against a `PredictionResult`.** `nids/api/rules.py`
imports nothing from `nids.api.inference` and never touches a served
model. A rule fires the same way whether the classifier agrees,
disagrees, or wasn't run at all — this is structural, not a behavior
that happens to hold today.

Verified live, not just asserted: a record engineered to match `R001`
(SYN-flood pattern) was sent to a real running server configured with an
impossibly high `alert_threshold` (so the ML path could never
independently alert). The classifier scored it `severity="low"`,
`risk_score.score=2.86` — genuinely unconcerned — and the response still
carried a real `alert_id`, persisted with `source="rule"`, `level=
"critical"`. The rule caught what the model didn't.

## Rule format

`src/nids/api/detection_rules.yaml` — a list of rules, each:

```yaml
- id: R001
  name: "SYN flood pattern"
  description: "..."
  severity: critical              # low | medium | high | critical
  conditions:                     # AND-combined -- every one must match
    - field: flag                 # a FEATURE_COLUMNS name
      operator: eq                # eq | gt | gte | lt | lte
      value: S0
    - field: count
      operator: gt
      value: 100
  mitre:                          # optional -- specified directly, not
    tactic: "Impact"               # derived from attack_category (a rule
    techniques:                    # has no PredictionResult to derive
      - id: "T1498"                # one from)
        name: "Network Denial of Service"
        url: "https://attack.mitre.org/techniques/T1498/"
```

Four starter rules ship in `detection_rules.yaml`, each exercising a
different field/operator combination and a distinct MITRE technique:
`R001` SYN flood (`flag`/`count`), `R002` root shell obtained
(`root_shell`), `R003` guest login to an authenticated service
(`is_guest_login`+`logged_in`), `R004` repeated failed logins
(`num_failed_logins`). Not an open-ended rule library — just enough to
prove the mechanism across categorical equality and numeric-threshold
matching.

**New dependency: `pyyaml`.** Already present in the environment
(pulled in transitively by another package) but not previously declared
in `pyproject.toml` — now declared explicitly rather than relying on an
undeclared transitive dependency. Installs nothing new.

`nids/api/rules.py` mirrors `nids.api.mitre`'s exact pattern: a static
data file + a pure loader, cached once per process (`load_rules()`).
`evaluate_rules(record)` returns the single highest-severity matching
rule (`nids.api.alerts.severity_rank`), or `None` — ties broken by
declaration order in the YAML file, so behavior never depends on
dict/set iteration order.

## Pipeline integration: two alerts can coexist

`nids.api.pipeline.finish_record` now computes **both** an ML alert
(`generate_alert`, unchanged) and a rule alert (`evaluate_rules` +
`generate_rule_alert`) for every record. This was a genuine design
decision, made explicitly with the user before implementing: when both
fire for the same record, **both persist independently** as separate
`AlertRecord` rows against the same `prediction_id` — `PredictionRecord.
alerts` was already a one-to-many relationship (no schema change
needed), just never exercised with more than one row before. Both are
notified independently too (each subject to its own
`notification_min_severity` gate).

The one place a single alert has to be named is `PredictResponse.
alert_id` (unchanged shape, for frontend/API compatibility) — it reports
whichever alert is higher severity, preferring the rule alert on an
exact tie (a deterministic signature hit over a probabilistic model
score). The full picture — every alert that fired — is always visible
via `GET /history/alerts`, filtered by `prediction_id`.

Verified live: a record matching `R001` sent to a server with
`alert_threshold=0` (so the ML path always alerts too) produced **two**
`AlertRecord` rows against one `prediction_id` — `("rule", "critical")`
and `("api", "low")` — neither silencing the other. `/predict/batch`
(which calls `finish_record` directly, not `process_record`, to preserve
its vectorized predict/explain calls) was verified the same way with a
3-row CSV: two ordinary rows got one alert each, the rule-matching row
got two.

## Persistence, dashboard, and notification compatibility

No schema changes. `Alert.source` already accepted any string (`Mapped[
str]`, no enum constraint) — `"rule"` is simply a new value alongside the
existing `"api"`/`"agent"`, and nothing in the codebase branches on a
specific `source` value (confirmed by inspection before this milestone
touched it): the frontend's `AlertHistoryItem.source`/
`PredictionHistoryItem.source` are typed as plain `string`, and
`nids_alerts_raised_total`'s `source` metric label is a separate,
independently-hardcoded string per route (`"api"`/`"agent"`), not
derived from `Alert.source` at all. A rule-sourced alert flows through
`AlertsPage`/`HistoryPage`/the notification dispatcher exactly like an
ML-sourced one, with zero frontend changes required.

## What's intentionally not here yet

- **No OR logic, no rule-authoring UI.** Conditions are AND-only, rules
  are a YAML file edited by hand — matches "keep the rule engine
  minimal, deterministic, human-readable." An admin UI for
  authoring/toggling rules is a separate, larger scope decision, not
  needed to prove the mechanism.
- **No per-alert increment on `nids_alerts_raised_total` when two
  alerts fire for one record.** The metric's existing semantics ("did
  this prediction raise at least one alert") are unchanged and still
  correct; a true "total alert objects" count would need a response-
  shape change this milestone deliberately avoided (see above).
- **`docs/API.md`'s "Multi-user deployments" bullet was stale** (said
  per-user auth/RBAC was "not addressed by anything built so far" — it
  was, in Milestone 11) — corrected alongside this milestone's own
  "Future endpoints" entry rather than left for a dedicated doc-only
  change.
