# Feature Pipeline Architecture

## The core rule

**Feature engineering logic exists in exactly one place:**
`src/nids/features/pipeline.py`'s `FeatureEngineer`. Every prediction path —
batch CSV analysis, PCAP-derived flow records, the live capture agent,
manual entry, demo replay — and every model (CatBoost, Random Forest,
LightGBM, XGBoost, or whatever comes next) reuses this same fitted object
unchanged. Nothing outside `nids/features/` should impute, scale, or encode
a feature. If a second implementation of "turn a connection record into
numbers" ever appears, that's a bug to fix, not a variant to maintain.

## Two responsibilities, one module

```
raw record (any source) --[contract]--> FeatureEngineer --[FeatureMatrix]--> training / inference
```

1. **`nids/features/contracts.py`** — the raw-record contract. Defines what
   every input adapter must produce: a `pandas.DataFrame` containing
   `nids.data.schema.FEATURE_COLUMNS` (the same 41 NSL-KDD-style connection
   features used by the training data), with numeric columns that are
   numeric or numeric-coercible. `validate_raw_records()` enforces this and
   raises a clear `ValueError` naming exactly which columns are missing or
   malformed — this is the error a broken adapter should hit, not a cryptic
   sklearn shape mismatch three layers down.

   It deliberately does **not** check categorical vocabulary. A `service`
   value never seen during training is an expected, not exceptional, event
   on live traffic — it's handled downstream by the encoder
   (`OneHotEncoder(handle_unknown="ignore")`), not rejected at the door.

2. **`nids/features/pipeline.py`** — `FeatureEngineer`, an sklearn
   `ColumnTransformer` (median-impute + scale for numeric columns,
   most-frequent-impute + one-hot for the three categorical columns)
   wrapped with a small, deliberately narrow API:

   - `fit(df)` — validate, then fit the transformer. Records fit metadata
     (schema version, sklearn version, fit timestamp, row count, output
     feature names) for auditability.
   - `transform(df)` — validate, then transform. Works identically whether
     `df` has 100,000 rows (a training run) or 1 row (a manual-entry form
     submission or a single live-captured connection).
   - `fit_transform(df)` — the two above, chained.
   - `save(path)` / `load(path)` — persist and restore a **fitted**
     pipeline via `joblib`, so training and every inference path load the
     exact same fitted transformer rather than re-fitting (re-fitting on
     inference data would silently produce a different — and wrong —
     encoding).

   Its output is a `FeatureMatrix` — a plain `(X: np.ndarray, feature_names:
   list[str], metadata: dict)` — nothing model-specific. `FeatureEngineer`
   never imports a model class and never reads a label column
   (`attack_type` / `is_attack` / `attack_category`); those stay the
   training pipeline's concern. This is what makes it model-agnostic in
   both directions: swappable models on one side, swappable label schemes
   on the other.

## Why this separation

- **Benchmarking models is a one-line swap.** A training script calls
  `FeatureEngineer().fit_transform(train_df)` once and hands `X` to
  whichever model it's evaluating. Comparing CatBoost vs. Random Forest vs.
  LightGBM vs. XGBoost never means touching preprocessing code — the
  feature matrix they receive is identical by construction.
- **No train/serve skew.** The exact fitted imputers/scalers/encoders used
  in training are the ones loaded (via `FeatureEngineer.load`) for every
  inference path. There's no separate "preprocessing for the API" reimplementation
  that can silently drift from what the model was trained on.
- **One place to harden.** Input validation, unseen-category handling, and
  future changes (new engineered features, different scaling) happen once
  and every consumer inherits the fix automatically.

## How each input path plugs in

None of these adapters exist yet beyond batch CSV (the rest are later
milestones) — this section is the contract they're expected to implement
when built, so the feature pipeline itself never needs to change to
accommodate them:

| Path | Adapter's job | Feeds into |
|---|---|---|
| Batch CSV upload | Parse the uploaded CSV, map/rename columns onto `FEATURE_COLUMNS` | `FeatureEngineer.transform(df)` |
| PCAP-derived flow records | Aggregate packets into flow-level stats matching `FEATURE_COLUMNS` semantics | same |
| Live capture agent | Compute the same per-connection stats in real time, one row at a time | same, one-row `df` |
| Manual entry (UI form) | Assemble a one-row DataFrame from form fields | same, one-row `df` |
| Demo replay | Replay stored/sample rows already in raw form | same |

Each adapter is expected to be a thin, source-specific translation layer.
The moment an adapter starts doing scaling, encoding, or imputation itself,
that's a sign logic leaked out of `nids/features/` and should move back in.

## Versioning and reproducibility

- `FEATURE_SCHEMA_VERSION` (in `pipeline.py`) bumps whenever the raw
  contract or the encoding scheme changes in a way that makes an old fitted
  pipeline invalid for new data, or vice versa. Persisted `FeatureMatrix`
  metadata and saved pipelines carry this version so a mismatch is
  detectable rather than silently wrong.
- A fitted `FeatureEngineer` is deterministic: given the same training data
  and the same scikit-learn version, `fit()` produces the same transformer
  state every time (no randomness in imputation/scaling/one-hot encoding).
- Saved pipelines (`FeatureEngineer.save`) are the unit of reproducibility
  for inference — always load the fitted pipeline that shipped with a given
  model, never re-fit a new one against production data.

## Tests

`tests/test_features.py` exercises the properties this design promises:
batch fit/transform, single-row transform (manual-entry shape), unseen
categorical values (live-capture shape), a rejected malformed input
(contract violation), and a save/load roundtrip producing bit-identical
output.
