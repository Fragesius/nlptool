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

No pytest required; the runner discovers all `test_*` functions under
`tests/`.
