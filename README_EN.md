# Chinese–English NLP Analysis Tool

A general-purpose desktop toolkit for quantitative analysis of Chinese and
English text: tokenization, POS/syntactic analysis (spaCy with a regex
fallback), readability metrics, concordance, Chinese–English sentence
alignment, stylometry (Burrows' Delta, hierarchical clustering), and
linguistic-fingerprint comparison.

The application ships with:

- a **GUI** (Chinese interface) for interactive analysis, and
- a **CLI experiment pipeline** (English) for batch stylometry experiments,
  designed so that results can be reproduced end-to-end from the command line.

> Note: the GUI interface is in Chinese; the CLI pipeline and its
> documentation are in English.

## Installation

Requires Python 3.8+.

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

The spaCy model is optional for the CLI pipeline (a regex tokenizer fallback
is used when spaCy or the model is missing), but recommended for full
fingerprint features.

## CLI experiment pipeline

The pipeline lives under `experiments/` and has two stages:

1. **slice** (`slice_corpus.py`) — cut raw texts into fixed-size word chunks;
2. **experiment** (`run_experiment.py`) — run the grouped stylometry
   experiment over the chunks and write all result artifacts.

An optional third tool, `weight_sensitivity.py`, reruns the
fingerprint-based group metrics under alternative composite-fingerprint
weights (see below).

There is also a lightweight single-folder Delta tool, `run_delta.py`
(no group structure; reads all `.txt` directly under `--input`).
**Deprecated since v2.4.0** — its functionality is fully covered by
`run_experiment.py`; use that instead.

### Input layout convention

Each **first-level subdirectory** of the experiment input root is one
**group**; every `.txt` file inside it is one sample of that group:

```
corpus/
├── group_A/
│   ├── work1.txt
│   └── work2.txt
└── group_B/
    ├── work1.txt
    └── work2.txt
```

Group names come from the directory names — nothing is hard-coded. When two
groups contain files with the same stem (e.g. parallel translations of the
same work), the signal-competition test pairs them automatically.

### Step 1: slice the corpus

```bash
python experiments/slice_corpus.py \
    --input corpus \
    --out corpus_sliced \
    --chunk-size 2000 \
    --clean
```

- `--chunk-size N`: target words per chunk (default 2000). A trailing chunk
  shorter than half the target size is discarded.
- `--clean`: empty the output directory before slicing (refuses dangerous
  paths such as the filesystem root or your home directory).

Output chunks are named `{stem}__chunk{NNN}.txt` and mirror the input
directory structure, so the group convention is preserved.

### Step 2: run the experiment

```bash
python experiments/run_experiment.py \
    --input corpus_sliced \
    --out experiment_output \
    --top-n 100 \
    --perm-n 10000 \
    --lang en \
    --report-lang en
```

- `--top-n`: number of most-frequent-word features for Burrows' Delta
  (default 100).
- `--perm-n`: permutation test iterations (default 10000).
- `--lang`: sample language for fingerprint features (`en` or `zh`,
  default `en`).
- `--report-lang`: template language of `report.md` (`zh` or `en`,
  default `zh`). Only template text differs; all numbers, tables and CSV
  files are identical either way.

### Output files

| File | Content |
| --- | --- |
| `delta_matrix.csv` | pairwise Burrows' Delta distance matrix |
| `dendrogram.png` | average-linkage hierarchical clustering dendrogram |
| `fingerprint_pairs.csv` | per-pair linguistic-fingerprint similarity (same/cross group) |
| `nn_predictions.csv` | 1-NN leave-one-out classification on the Delta matrix |
| `signal_competition.csv` | per-work original-vs-group signal competition results |
| `report.md` | Markdown summary of all statistics, tests and conclusions |

### Step 3 (optional): weight sensitivity analysis

The composite fingerprint weights (function words 0.30, punctuation 0.15,
word bigrams 0.15, word length 0.10, sentence length 0.10, TTR 0.10,
char 4-grams 0.05, hapax ratio 0.05) are heuristic. To show that the
conclusions do not depend on them, `weight_sensitivity.py` reruns the
fingerprint-based group metrics — within/between-group mean distance,
Cohen's d, the signal competition test and 1-NN leave-one-out accuracy —
under alternative weighting schemes, at one or more chunk scales:

```bash
python experiments/weight_sensitivity.py \
    --scale 1k=corpus_sliced_1000 \
    --scale 2k=corpus_sliced_2000 \
    --scale 4k=corpus_sliced_4000 \
    --weights all \
    --out sensitivity_out \
    --report experiment_output_2000/report.md
```

- `--scale NAME=DIR`: one grouped input directory per scale (repeatable;
  each `DIR` follows the same input layout convention as
  `run_experiment.py`). Scale names must map to **distinct** directories —
  pointing two scales at the same directory is rejected, because it would
  silently produce byte-identical rows across "scales".
- `--weights {all,default,uniform,lodo,single,random}`: `all` (the
  default) runs every family in one pass — 38 variants (1 `default` +
  1 `uniform` + 8 `lodo` + 8 `single` + 20 `random`); `default` keeps the
  existing weights (identical to running without the switch); `uniform`
  weights all eight dimensions 1/8; `lodo` zeroes one dimension at a time
  and renormalizes the rest in their original proportions (8 variants);
  `single` uses one dimension at a time (8 variants); `random` perturbs
  each weight uniformly within [0.5w, 1.5w] and renormalizes (20 seeds
  starting at 20260818, each on its own RNG stream).
- `--report`: appends a "Weight sensitivity" section (summary table plus
  a one-sentence conclusion) to an existing `report.md`; the append is
  pure — no existing content is modified.

Output: `weight_sensitivity.csv` (overwritten on each run), a long table
with one row per variant x scale — 114 rows for `all` x three scales —
and columns `variant, scale, within, between, d,
competition_wins, knn_acc, knn_baseline`. Note that the headline
Burrows' Delta pipeline (Delta matrix, Delta-based signal competition,
dendrogram) never reads the fingerprint weight configuration, so those
results are weight-independent by construction.

### Step 4 (optional): paper data exports (v2.3.1)

`export_paper_data.py` writes the paper's data artifacts in one pass from
the raw corpus root (one subdirectory per group, full unsliced texts):

```bash
python experiments/export_paper_data.py --input corpus \
    --data-out data --control-out results/tokenizer_control
```

- `data/mfw100.txt` — the 100 MFW wordlist. Merge convention: all full
  unsliced texts of all groups are pooled, tokenized with the stylometry
  tokenizer (`[A-Za-z]+`, lowercased), ranked by count descending with
  alphabetical tie-break — identical to the feature selection inside
  `build_freq_table`.
- `data/delta_matrix_1k.csv` / `data/delta_matrix_2k.csv` — chunk-level
  Delta matrices at the 1k/2k scales; byte-compatible with the existing
  `delta_matrix_4k.csv` (UTF-8 BOM, empty corner cell, 6 decimals); the
  100 MFW features are refit per scale on the chunks, as in
  `run_experiment.py`.
- `data/feature_scores.csv` — one row per chunk x scale (1k/2k/4k): the
  eight per-dimension fingerprint scores (chunk vs own-group centroid,
  the unweighted components of `weighted_cosine_similarity`) plus the
  weighted total.
- `results/tokenizer_control/<scale>/` — a full pipeline rerun with the
  tokenizer changed to `[A-Za-z']+` (contractions kept), CSVs only
  (delta_matrix / nn_predictions / signal_competition /
  fingerprint_pairs); a control check, not part of the paper's main
  tables. Use `--skip-control` to export only the `data/` artifacts.

## Reproducing a dual-translation experiment

A typical use case is comparing two groups of parallel translations (e.g.
two translators of the same works). The corpus itself is **not** distributed
with this repository — translation texts are usually copyright-protected and
must be obtained by the user. To reproduce such an experiment:

1. **Collect the texts.** Obtain plain-text (`.txt`, UTF-8) versions of both
   translation groups yourself.
2. **Clean each file.** Remove everything that is not translated body text:
   prefaces, translator's notes, footnotes/endnotes, copyright pages, tables
   of contents, and running headers. The two groups should contain the same
   works, one file per work, with matching file stems.
3. **Arrange by group.** Place the files as
   `corpus/<group_name>/<work>.txt` (one first-level subdirectory per group,
   as shown above).
4. **Slice and run at multiple scales.** Chunk size affects stylometric
   results, so the standard recipe repeats the pipeline at several scales;
   always pass `--clean` before re-slicing into the same directory:

   ```bash
   for size in 1000 2000 4000; do
       python experiments/slice_corpus.py --input corpus \
           --out corpus_sliced_$size --chunk-size $size --clean
       python experiments/run_experiment.py --input corpus_sliced_$size \
           --out experiment_output_$size --lang en --report-lang en
   done
   ```

5. **Compare across scales.** A robust group-level style signal should
   appear consistently across chunk sizes in `report.md` (within- vs
   cross-group Delta, 1-NN accuracy, fingerprint tests).

## Running the tests

```bash
python run_tests.py
```

The runner is a thin pytest wrapper (pytest is declared in
`requirements.txt`); it is equivalent to `python -m pytest tests/`.

## Changelog note: v2.3.2 — Wilcoxon correctness fix

- Fixed two deviations in
  `core.linguistic_fingerprint.wilcoxon_signed_rank_test`: the average-rank
  formula `(j+k+2)/2` → `(j+k+1)/2`, and the rank/sign mispairing caused by
  `zip(ranks, indexed)` — signed ranks are now accumulated directly on the
  sorted sequence (same standard definition as
  `experiments/story_stats.wilcoxon_stats`). The normal survival function now
  uses `math.erfc` (previously an Abramowitz & Stegun approximation with
  ~1.5e-7 error).
- Scope: on rerun, the GUI fingerprint page's `p_value_wilcoxon` and the
  experiment pipeline's chunk-level `p_wilcoxon` (one of report.md's headline
  statistics) are updated to the standard definition; the paper's
  story-level tests go through `story_stats.wilcoxon_stats` and are
  unchanged; all other outputs (Delta matrices, signal competition,
  dendrogram, 1-NN, ...) are unaffected.
- Both implementations now document that p is a normal approximation (no
  continuity correction, no tie variance correction; with ties this differs
  from scipy's tie-corrected values — see the test docstrings).
- New `tests/test_wilcoxon.py`: hand-calc assertion (`[1,2,3,4,-1]` →
  W=1.5), 200 random groups cross-checked against `story_stats`, and 200
  against `scipy.stats.wilcoxon` (skipped when scipy is absent).

## Changelog note: v2.4.0 — GUI hardening & engineering cleanup

Guardrail: after all changes, the full three-scale pipeline (1k/2k/4k
run_experiment) plus the 38-variant weight sensitivity was rerun on the real
corpus and byte-diffed against the v2.3.2 baseline — all output directories
byte-identical (delta / signal_competition / story_level_tests /
weight_sensitivity CSVs, report.md, dendrogram).

- **GUI fingerprint analysis 21–26x faster**: `analyze_fingerprint` now
  batch-tokenizes all segments (`tokenize_many` + `extract_sentence_stats_many`),
  reuses that tokenization for the global vocab, and runs spaCy with
  `disable="all"` (tokenizer only — this path consumes just `Token.text`,
  verified token-for-token identical to the full pipeline). Measured
  (A ≈ 42k/70k/98k chars): 18.9s→0.74s / 20.0s→0.90s / 29.7s→1.41s.
  A/B gate: every feature field and statistic identical, tolerance 0 (EN+ZH).
- **Cancel button actually cancels** (`ui/async_runner.py`): cancelling bumps
  the task generation so late results are dropped; new `on_cancel` callback
  (fired exactly once) and `report_progress(done, total)` (determinate
  per-chunk progress). Fingerprint and batch analysis check for cancellation
  per chunk/file and stop within a second; the UI is immediately reusable.
- **`ui/tabs.py` (2360 lines) split into the `ui/tabs/` package**: one module
  per tab + shared `widgets.py`; `__init__.py` re-exports everything, so
  `main_window.py` is untouched. Pure move.
- Minor: `analyze_basic` no longer tokenizes every sentence to fill the
  unread `Sentence.tokens`; VADER is now a thread-safe lazy singleton (scores
  unchanged; SnowNLP instantiation measured at microseconds, kept per-call
  with a comment); `run_delta.py` is deprecated (use `run_experiment.py`)
  with a smoke test; `run_tests.py` is now a thin pytest wrapper.
- Tests: 92 → 99 (6 new cancellation-semantics + 1 run_delta smoke).

## Data & copyright

- The code is MIT-licensed; `experiments/sample_corpus/` is **synthetic**
  generated text and contains no real work.
- Research corpora (e.g. dual translations of the same novels) are **not**
  distributed with this repository: translation texts remain copyrighted by
  their translators/publishers. Obtain them legally, use them for personal
  research only, and never commit source texts to this or any public
  repository (`corpus/` is gitignored by default).
- The exports under `data/` and `results/` are **derived statistics**
  (word lists, distance matrices, per-dimension scores) with no expressive
  content from the source texts, and are safe to publish with the paper.

## License

MIT © 2026 Fragesius
