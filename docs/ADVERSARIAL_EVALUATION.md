# Adversarial Robustness Evaluation

**Status: Milestone 17.** An offline research tool, not a platform
feature: it attacks the project's own already-trained classifier with
bounded, realistic feature-space perturbations of real NSL-KDD attack
rows, and reports how often the classifier's verdict flips from attack to
normal. Nothing in `nids.api`, `nids.training`, or production inference
is touched, imported, or configured differently by this evaluation —
`src/nids/evaluation/` is a standalone subpackage that loads an
already-saved run (`nids.training.artifacts.load_run`) and runs entirely
offline, in-process, against no external target.

Chosen as the next milestone by explicit user request (an "approved M17
plan"), not by the evaluate-the-codebase-gap process used for milestones
7–16 — see [[milestone-status]] for that pattern's history.

## Why this matters

Every prior milestone measured *accuracy*: does the classifier get the
right answer on held-out data drawn from the same distribution it was
trained on. This milestone asks a different question: **how much does an
attacker have to change about their traffic, within realistic bounds, to
get past the classifier while the attack still happens?** A model with
99% accuracy that flips to "normal" after a handful of bounded, plausible
tweaks is a materially different security posture than one that doesn't
— accuracy alone can't distinguish them.

## Scope decisions (made explicitly, before writing any code)

- **Target: `rf-binary-verify` only.** Random Forest, `is_attack` binary
  label. The operationally primary question is "does this get flagged as
  an attack at all," not per-category classification; CatBoost and
  multiclass runs are a natural v2 extension, not built here.
- **Attack search: random search only.** A greedy/hill-climbing
  stronger-adversary pass was considered and deferred — random search is
  cheap, trivially reproducible with a fixed seed, and gives one clear
  number per budget level. See [Attack methodology](#attack-methodology)
  for why this is the right tool for tree ensembles specifically.
- **Code location: new `src/nids/evaluation/` subpackage**, mirroring
  `nids.training`'s shape (`perturbation.py`, `attack.py`, `report.py`,
  `cli.py`/`__main__.py`), fully decoupled from `nids.api` — it builds its
  own `shap.TreeExplainer` rather than importing `nids.api.explain`, and
  never imports anything under `nids.api`.

## The threat model: what "attacker-controllable" means here

NSL-KDD's 41 connection-level features aren't equally within an
attacker's power to change. An attacker crafts the packets they send —
but many features are *derived statistics* (rates over a windowed set of
surrounding connections) or *outcomes* of whether the attack itself
succeeded, not independent dials. Perturbing those wouldn't model a real
adversary; it would just relabel the row. The allowlist below
(`nids.evaluation.perturbation`) is the operating definition of
"realistic" for this evaluation.

### Tier 1 — freely adjustable within bounds

Attacker directly crafts these at the packet/flow-shaping level (pad a
payload, throttle the connection rate, fragment packets):

`duration`, `src_bytes`, `wrong_fragment`, `urgent`, `count`, `srv_count`,
`dst_host_count`, `dst_host_srv_count`

Bounded to `[min, upper]` observed on the **training split only** (never
the test split being attacked — bounds mustn't be fit on the data the
attack is evaluated against). `upper` is the **99.9th percentile, not the
raw max** — see [The outlier bound](#the-outlier-bound-a-real-bug-this-caught)
below for why that distinction mattered in practice. The clip ceiling for
a given row is `max(upper, that row's own original value)`, so a
legitimately large original value is never shrunk by an unlucky delta —
only how far a value can *additionally* move is bounded by the quantile.

### Tier 2 — rate features, smaller budget, `[0, 1]`-bounded

Attacker influences these via traffic shaping (e.g. avoiding failed
connections lowers `serror_rate`) rather than setting them directly —
they're computed from a *window of surrounding connections*, not just the
row being perturbed. Attacking them per-row in isolation is a documented
simplification of this evaluation, not a claim that a single packet
change produces this effect in isolation:

`serror_rate`, `srv_serror_rate`, `rerror_rate`, `srv_rerror_rate`,
`same_srv_rate`, `diff_srv_rate`, `srv_diff_host_rate`,
`dst_host_same_srv_rate`, `dst_host_diff_srv_rate`,
`dst_host_same_src_port_rate`, `dst_host_srv_diff_host_rate`,
`dst_host_serror_rate`, `dst_host_srv_serror_rate`,
`dst_host_rerror_rate`, `dst_host_srv_rerror_rate`

Perturbed by `± epsilon` absolute, clipped to `[0, 1]`.

### Tier 3 — decrease-only stealth features

Activity-count "footprint" features. An attacker can plausibly *suppress*
these (create fewer files, spawn fewer shells) but fabricating them
upward isn't a realistic evasion move without a materially different
attack, so these are decrease-only, floored at 0, budgeted as a fraction
of the row's own original value:

`num_file_creations`, `num_shells`, `num_access_files`, `num_root`,
`hot`, `num_failed_logins`

### Excluded entirely

- `protocol_type`, `service`, `flag` — categorical, excluded per explicit
  instruction; no attack-specific carve-out in v1.
- `land` — defines the land-attack itself; flipping it for a non-land row
  is meaningless, and flipping it for a land row undoes the attack rather
  than evading detection of it.
- `logged_in`, `root_shell`, `su_attempted` — attack-*success outcomes*,
  not attacker dials. Forcing `root_shell` to 0 on a successful
  privilege-escalation row doesn't model an evasive attacker; it changes
  what happened.
- `is_host_login`, `is_guest_login` — account identity, not traffic
  shape.
- `num_compromised` — an outcome count, same reasoning as `root_shell`.
- `num_outbound_cmds` — constant `0` across all of NSL-KDD (verified
  empirically); zero variance, nothing to perturb.
- `dst_bytes` — the *server's* response size, only indirectly
  attacker-influenced (which resource they request, whether they trigger
  an error page). Excluded from the default allowlist as not directly
  attacker-set; a defensible target for a future ablation, not v1.

Allowlisted (29) + excluded (12) accounts for all 41 `FEATURE_COLUMNS`
(`test_allowlist_plus_excluded_covers_every_feature_column` in
`tests/test_evaluation_perturbation.py` enforces this stays true).

## Preserving feature relationships: constraint repair

A handful of "obvious feature relationships" must survive independent
per-feature sampling, or a "perturbed" row wouldn't correspond to
anything a real connection could produce:

- `srv_count <= count`, `dst_host_srv_count <= dst_host_count` — repaired
  by clipping the smaller-side feature down.
- Rate pairs that shouldn't sum past 1.0 under the original KDD
  definitions (`same_srv_rate`+`diff_srv_rate`,
  `serror_rate`+`rerror_rate`, and their `srv_`/`dst_host_` variants) —
  repaired by proportionally rescaling both down.

Repair is **clip/rescale, not reject-and-resample** — a deliberate
simplicity choice (`nids.evaluation.perturbation.repair`). A
reject-and-resample approach would be marginally more "pure" (never
silently move a sampled value) but adds a retry loop and an unbounded
worst-case sampling cost for a first version; the two are behaviorally
close for the small perturbation budgets used here.

## Attack methodology

Tree ensembles (Random Forest, CatBoost) aren't differentiable the way
neural networks are — gradient-based attacks (FGSM, PGD) don't apply
without extra structure (e.g. a surrogate model). The standard approach
for tree ensembles is a **black-box query attack**: sample candidates,
ask the model what it thinks, keep the best one. This evaluation reuses
the model's real `predict`/`predict_proba` and the row's real, already-
fitted `FeatureEngineer.transform` — the exact same call production
`nids.api.inference` makes — so what the attack sees is identical to what
a served request would see.

**Random search** (`nids.evaluation.attack.run_attack`): for each row,
sample `n_trials` independent bounded candidates (every allowlisted
feature perturbed per the tiers above), transform and predict all of them
in one batch, and report the one that dropped the model's attack-class
probability the most. "Evaded" means at least one candidate's *predicted
label* — not just its probability — flipped to normal; a probability dip
that doesn't cross the decision boundary isn't evasion.

Only rows the model **currently, correctly predicts as an attack**
(true positives at baseline) are attacked — perturbing a row the model
already misses doesn't measure evasion, it's already a free false
negative. Both counts are reported (`evasion_summary`'s
`baseline_false_negatives` / `baseline_fn_rate`) so an evasion rate is
never read without that context.

**Performance**: candidate generation and prediction are fully vectorized
per budget level — one `FeatureEngineer.transform` call for
`n_true_positives * n_trials` rows, not one call per row. On the full
`KDDTest+.txt` true-positive set (~10,300 rows) with `n_trials=30`, one
budget level runs in a few seconds; `--n-trials 200` (the CLI default)
and 3 budget levels against the full set takes longer — use `--max-rows`
for a fast smoke run.

## The outlier bound: a real bug this caught

The first real run against `rf-binary-verify` (not a synthetic test)
surfaced a genuine flaw in the initial design: `src_bytes`'s training-split
max is **1,379,963,888** against a 99.9th percentile of **~2,194,619** — a
handful of known NSL-KDD data-quality outlier rows. With bounds fit as
raw `[min, max]`, even the smallest budget (`epsilon=0.05`) computed a
window of `0.05 * 1.38e9 ≈ 69,000,000` — a "bounded, realistic"
perturbation that could move `src_bytes` by 69 million bytes is neither.
`FeatureBounds.from_train_df` was changed to use a 99.9th-percentile upper
bound instead of the raw max (see the class docstring in
`nids.evaluation.perturbation` for the full reasoning and why this changes
nothing for `count`/`srv_count`/`dst_host_count`/`dst_host_srv_count`,
whose 99.9th percentile already equals their max — KDD caps those at
511/511/255 by construction). Confirmed via a real re-run:
`src_bytes`'s mean perturbation magnitude among successful evasions
dropped from ~108.7 million to ~155,861 after the fix.

## Metrics

- **`evasion_summary`** — overall + per-budget evasion rate, alongside
  the baseline (unperturbed) false-negative rate for context, and the
  mean attack-probability drop per budget.
- **`category_breakdown`** — evasion rate per NSL-KDD attack category
  (`dos`/`probe`/`r2l`/`u2r`), read from the raw test file's
  `attack_category` purely for reporting — it's never fed to the model,
  which only ever sees `is_attack`.
- **`feature_association`** — ranks allowlisted features by how often
  they appear in a *successful* evasion and the average magnitude of the
  change: which knobs an adversary actually needed to turn.
- **`shap_overlap`** — for every successfully-evaded row, compares that
  row's *original* (pre-perturbation) SHAP top-N features (via a
  self-built `shap.TreeExplainer`, the same normalization logic as
  `nids.api.explain`, duplicated rather than imported to keep this
  package offline-only) against the features the attack actually
  perturbed. This is the direct answer to "does the adversary have to
  touch the features the model relies on most, or find a cheap side
  door SHAP wouldn't have flagged."

## A known limitation: non-monotonic evasion rate

Because this is fixed-`n_trials` random search, evasion rate is **not
guaranteed to increase monotonically with budget** — a larger `epsilon`
enlarges the search *volume* without enlarging the *sample count*, so the
same `n_trials` explores it more thinly. This was observed directly in a
smoke run (`n_trials=30`, 25 rows): evasion rate went 0.44 → 0.36 → 0.28
across epsilon 0.05 → 0.15 → 0.30. Larger `--n-trials` values reduce this
effect; it isn't eliminated by construction. Report multiple budgets as
independent measurements, not as a guaranteed-monotonic curve.

## Running it

```bash
python -m nids.evaluation \
  --run-id rf-binary-verify \
  --budgets 0.05,0.15,0.30 \
  --n-trials 200 \
  --seed 42 \
  --output evaluation_report.json
```

Key flags: `--max-rows N` attacks a deterministic random sample of N true
positives instead of the full set (fast smoke run); `--test-file
difficulty-21` swaps in `KDDTest-21.txt`, the harder difficulty-21-
excluded split; `--top-n-shap N` controls how many SHAP features count as
"top" for the overlap metric. The evaluator refuses to run against a
multiclass (`attack_category`) run — see
[Scope decisions](#scope-decisions-made-explicitly-before-writing-any-code).

## Tests

`tests/test_evaluation_perturbation.py` (pure — tiers, bounds, repair,
outlier-quantile robustness), `tests/test_evaluation_attack.py` (a real
tiny Random Forest fit on `tests/fixtures/sample_kdd_cv.txt`, run-attack
accounting, `--max-rows` determinism), `tests/test_evaluation_report.py`
(pure metric aggregation + a real-model `shap_overlap` pass),
`tests/test_evaluation_cli.py` (argument parsing, report shape, the
multiclass rejection).
