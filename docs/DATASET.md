# Dataset Decision: NSL-KDD

**Status: frozen.** This is the dataset for Milestone 1 and the near-term
supervised-learning work. Revisiting it is a deliberate decision, not a
default.

## What we use

- **Dataset:** NSL-KDD (train/test splits derived from KDD Cup 1999, curated
  by Tavallaee, Bagheri, Lu & Ghorbani, 2009, University of New Brunswick /
  Canadian Institute for Cybersecurity).
- **Source of truth:** GitHub mirror
  [`jmnwong/NSL-KDD-Dataset`](https://github.com/jmnwong/NSL-KDD-Dataset),
  pinned to commit `9d544d0eb9b87d7e2f43ff65733bdb644631d12f`.
- **Files used:** `KDDTrain+.txt`, `KDDTrain+_20Percent.txt`, `KDDTest+.txt`,
  `KDDTest-21.txt`.
- **Integrity:** each file is checksum-verified (SHA-256) against a value
  recorded in `src/nids/data/download.py` at the time the mirror was
  inspected. A mismatch aborts the fetch instead of silently using different
  data.

| File | Rows | SHA-256 |
|---|---|---|
| `KDDTrain+.txt` | 125,973 | `1b86d2f957b33082081bba410fe129b475efebcc13c9014c3f447c8271aadf95` |
| `KDDTrain+_20Percent.txt` | 25,192 | `7ea86479faab5ca2190b7f18b4982fb058ce5bf2b46e0e1017d0d9ef90f9c16e` |
| `KDDTest+.txt` | 22,544 | `fa46b0935342616aa83b7c2578db355b6a7aaabbc492248172c7a1e8b7ab8f84` |
| `KDDTest-21.txt` | 11,850 | `746993ac9e25868827cacf09eab450050a2a1056e1ce48a1ad39f5dc801d531d` |

Note: `KDDTrain+_20Percent.txt` has exactly 25,192 rows, matching the dataset
statistics already documented in the project's top-level `README.md` — the
prior prototype (`legacy/`) was already built against this same file.

## Why NSL-KDD

- It's the dataset the existing prototype (Random Forest + Apriori, see
  `legacy/` and `README.md`) was already validated against, so switching
  wouldn't be free and isn't necessary for Milestone 1's goals.
- It directly fixes the two best-documented flaws of raw KDD Cup 1999 (its
  predecessor): duplicate records that bias classifiers toward frequent
  patterns, and a test set with no duplicates of the training set. This makes
  reported metrics harder to game via memorization.
- Train/test sizes (125,973 / 22,544) are small enough to run full-dataset
  experiments without subsampling, so results are exactly reproducible run to
  run — important for comparing model iterations honestly.
- It's a standard benchmark with decades of published baselines, so our
  model's numbers are checkable against a large body of prior work.

## Why not the alternatives

- **Official UNB/CIC host (`unb.ca/cic/datasets/nsl.html`).** This is the
  authoritative origin and is credited as such above, but the page's actual
  download redirects to an access-gated file host (intermittently a
  SharePoint/OneDrive link) with no stable, scriptable URL and no published
  checksums. That fails the reproducibility and ease-of-cloning criteria: a
  setup script can't depend on a link that requires manual, interactive
  access and may change without notice. We are not attempting to
  reverse-engineer or bypass that gate — see the mirror-selection rationale
  below.
- **CICIDS2017 / UNSW-NB15 / other modern traffic captures.** These are
  reasonable datasets for a future milestone (more realistic modern traffic,
  richer flow features) but are multi-GB downloads with their own access
  friction, and switching now would invalidate the existing prototype's
  results without buying anything for Milestone 1, which is about
  standing up the pipeline, not maximizing realism.
- **Kaggle re-uploads.** Multiple Kaggle datasets host NSL-KDD-derived CSVs,
  but several have been re-columned, re-labeled, or partially deduplicated by
  the uploader without documentation of what changed, which undermines
  "correctness and authenticity" (our top-priority criterion). We could not
  find one with a clear, verifiable chain back to the original files.
- **Other GitHub mirrors (e.g. `HoaNP/NSL-KDD-DataSet`).** Also legitimate
  copies of the same data. `jmnwong/NSL-KDD-Dataset` was preferred because
  its README is explicit about provenance (an archived copy of the original
  UNB files, sourced via the Wayback Machine when the official link was
  unreachable) and it has wider community adoption (more stars/forks), which
  matters for long-term availability — a well-forked repo is unlikely to
  disappear.

## Known limitations

- **Synthetic, 1998-vintage traffic.** NSL-KDD's connection records derive
  from the DARPA/KDD-99 simulation. Feature distributions (protocols,
  service names, byte counts) do not reflect present-day network traffic,
  and models trained on it will not directly generalize to production
  traffic without revalidation on modern data.
- **Class imbalance and unseen attack types.** The test split intentionally
  includes attack types absent from the training split, to measure
  generalization to novel attacks — this is by design, not a data quality
  bug, but it means a naive classifier will show a recall gap on the test
  set that a train-only cross-validation would not reveal.
- **Coarse feature set.** No packet-level or timing-jitter detail; several
  numeric features (`num_outbound_cmds`, `is_host_login`) are near-constant
  and carry little signal.
- **Mirror, not origin.** We depend on a third-party GitHub mirror for
  availability. The checksums in `download.py` pin us to a specific known
  copy; if that mirror disappears, any bit-identical copy of the same
  checksummed files remains valid, since correctness is defined by the hash
  rather than the host.

## Preprocessing strategy

Implemented in `src/nids/data/`:

- `schema.py` — canonical column names (41 features + `attack_type` +
  `difficulty`), and the `attack_type -> attack_category` taxonomy
  (`normal` / `dos` / `probe` / `r2l` / `u2r`) used throughout the NSL-KDD
  literature.
- `download.py` — fetches the four files from the pinned mirror commit,
  verifies each against its recorded SHA-256, and refuses to proceed on a
  mismatch.
- `loader.py` — reads a raw file into a `pandas.DataFrame`, types the three
  categorical columns (`protocol_type`, `service`, `flag`) as `category`,
  validates every `attack_type` value is recognized, and derives:
  - `attack_category` (5-class taxonomy, for multi-class work), and
  - `is_attack` (binary 0/1, for the current binary classifier).

Further preprocessing (one-hot/target encoding of categoricals, numeric
scaling, feature selection) belongs in a downstream `nids.features` step, not
in the loader — the loader's job is only to produce a clean, correctly typed,
fully labeled DataFrame from the raw files.

## Reproducing the dataset setup

```bash
# from the repo root, with the project's venv active
python -m nids.data.download
```

This populates `data/raw/nsl-kdd/` with the four verified files (git-ignored;
see `.gitignore`). Then, in Python:

```python
from nids.data import load_train, load_test

train_df = load_train(full=True)   # or full=False for the 20% subsample
test_df = load_test()              # or exclude_difficulty_21=True for KDDTest-21
```

Both loaders raise `FileNotFoundError` with a pointer back to the download
command if the raw files aren't present yet, and `ValueError` if an
unrecognized `attack_type` shows up (signaling the mirror's data no longer
matches the taxonomy in `schema.py`).
