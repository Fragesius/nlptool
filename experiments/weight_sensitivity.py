"""Weight sensitivity analysis for the composite fingerprint (v2.3.0).

The composite fingerprint weights (function words 0.30, punctuation 0.15,
word bigrams 0.15, word length 0.10, sentence length 0.10, TTR 0.10,
char 4-grams 0.05, hapax ratio 0.05; weighted cosine) in
``core.linguistic_fingerprint.FEATURE_WEIGHTS`` are a heuristic choice.
This module reruns the group-level metrics under alternative weighting
schemes to show the conclusions do not depend on that choice.

Schemes (``--weights``):

- ``all`` (default): every family below in one run — 38 variants
  (1 default + 1 uniform + 8 lodo + 8 single + 20 random);
- ``default``: the existing weights — results are identical to the
  fingerprint metrics produced by ``run_experiment.py`` without any switch;
- ``uniform``: all eight dimensions weighted 1/8;
- ``lodo``: leave-one-dimension-out — one dimension zeroed, the rest
  renormalized in their original proportions (8 variants);
- ``single``: one dimension at a time, weight 1 (8 variants);
- ``random``: each weight perturbed uniformly within [0.5w, 1.5w] and
  renormalized; 20 seeds starting at 20260818, each seed drawing from its
  own ``random.Random`` stream (the global RNG state is never touched).

For every variant x scale the weighted-cosine composite fingerprint is
used to recompute: within/between-group mean distance (1 - similarity),
Cohen's d (same convention as ``run_experiment.py``: same-translator vs
cross-translator pair similarities, pooled sample standard deviation),
the signal competition test (original-signal wins) and 1-NN
leave-one-out accuracy with its majority-class baseline — the last two
reused from ``experiments.group_metrics`` on the fingerprint distance
matrix.

Output: ``weight_sensitivity.csv`` (long table: variant, scale, within,
between, d, competition_wins, knn_acc, knn_baseline) and, when
``--report`` is given, a "Weight sensitivity" section *appended* to that
report.md (existing content is never modified).

Usage:
    python experiments/weight_sensitivity.py \
        --scale 1k=corpus_sliced_1000 --scale 2k=corpus_sliced_2000 \
        --scale 4k=corpus_sliced_4000 \
        --weights all --out sensitivity_out \
        --report experiment_output_2000/report.md
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Allow running directly from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.analyzer import tokenize_many  # noqa: E402
from core.linguistic_fingerprint import (  # noqa: E402
    FEATURE_WEIGHTS,
    SegmentInfo,
    build_global_vocab,
    cohens_d,
    extract_features,
    extract_sentence_stats_many,
    weighted_cosine_similarity,
)
from experiments.group_metrics import (  # noqa: E402
    nearest_neighbor_loo,
    signal_competition,
)

__all__ = [
    "DIMENSIONS",
    "RANDOM_BASE_SEED",
    "RANDOM_VARIANTS",
    "SCHEMES",
    "variants_for_scheme",
    "extract_corpus_features",
    "evaluate_variant",
    "run_sensitivity",
    "append_report_section",
]

# Fixed dimension order (FEATURE_WEIGHTS insertion order).
DIMENSIONS: Tuple[str, ...] = tuple(FEATURE_WEIGHTS)

# "all" runs every family in one pass: default + uniform + 8 lodo
# + 8 single + 20 random = 38 variants.
SCHEMES = ("all", "default", "uniform", "lodo", "single", "random")

RANDOM_BASE_SEED = 20260818
RANDOM_VARIANTS = 20

CSV_COLUMNS = [
    "variant", "scale", "within", "between", "d",
    "competition_wins", "knn_acc", "knn_baseline",
]


# =============================================================================
# Weight variant generation
# =============================================================================


def _renormalize(weights: Dict[str, float]) -> Dict[str, float]:
    """Scale weights to sum 1, preserving proportions (fixed key order)."""
    total = sum(weights[k] for k in DIMENSIONS)
    if total <= 0:
        raise ValueError("weight vector sums to zero, cannot renormalize")
    return {k: weights[k] / total for k in DIMENSIONS}


def variants_for_scheme(
    scheme: str,
    n_random: int = RANDOM_VARIANTS,
    base_seed: int = RANDOM_BASE_SEED,
) -> List[Tuple[str, Dict[str, float]]]:
    """Return the ``(variant_name, weights)`` list for one scheme.

    :param scheme: one of ``SCHEMES``; "all" concatenates every family
        (default + uniform + lodo + single + random = 38 variants)
    :param n_random: number of ``random`` variants
    :param base_seed: first seed of the ``random`` scheme; each variant i
        uses its own ``random.Random(base_seed + i)`` stream, so the
        global RNG state is never touched and results are reproducible
    :return: ordered list of variants (1 for default/uniform, 8 for
        lodo/single, ``n_random`` for random, 1+1+8+8+``n_random`` for all)
    """
    if scheme == "all":
        return (variants_for_scheme("default")
                + variants_for_scheme("uniform")
                + variants_for_scheme("lodo")
                + variants_for_scheme("single")
                + variants_for_scheme("random", n_random, base_seed))
    if scheme == "default":
        return [("default", dict(FEATURE_WEIGHTS))]
    if scheme == "uniform":
        w = 1.0 / len(DIMENSIONS)
        return [("uniform", {k: w for k in DIMENSIONS})]
    if scheme == "lodo":
        variants = []
        for dim in DIMENSIONS:
            w = {k: (0.0 if k == dim else FEATURE_WEIGHTS[k])
                 for k in DIMENSIONS}
            variants.append((f"lodo_{dim}", _renormalize(w)))
        return variants
    if scheme == "single":
        return [
            (f"single_{dim}",
             {k: (1.0 if k == dim else 0.0) for k in DIMENSIONS})
            for dim in DIMENSIONS
        ]
    if scheme == "random":
        variants = []
        for i in range(n_random):
            seed = base_seed + i
            rng = random.Random(seed)  # independent stream per seed
            w = {k: FEATURE_WEIGHTS[k] * rng.uniform(0.5, 1.5)
                 for k in DIMENSIONS}
            variants.append((f"random_{seed}", _renormalize(w)))
        return variants
    raise ValueError(
        f"unknown weights scheme: {scheme!r} (choose from {SCHEMES})"
    )


# =============================================================================
# Feature extraction (mirrors run_experiment.py step (c))
# =============================================================================


def extract_corpus_features(input_dir: Path, lang: str = "en"):
    """Load a grouped corpus and extract one FeatureVector per sample.

    Same extraction path as ``run_experiment.run`` (batch tokenization,
    shared global vocab), so the ``default`` variant reproduces the
    existing fingerprint numbers exactly.

    :param input_dir: grouped input root (one subdirectory per group)
    :param lang: sample language ("en" or "zh")
    :return: ``(labels, group_of, fvs)`` — sample labels, group mapping
        and ``{label: FeatureVector}``
    """
    # Lazy import: run_experiment pulls in matplotlib (via viz.dendrogram)
    # at module level, but the sensitivity analysis draws no figures.
    from experiments.run_experiment import load_groups

    groups = load_groups(Path(input_dir))

    texts: Dict[str, str] = {}
    group_of: Dict[str, str] = {}
    for gname, samples in groups.items():
        for label, text in samples.items():
            texts[label] = text
            group_of[label] = gname
    labels = list(texts.keys())

    text_list = [texts[label] for label in labels]
    token_list = tokenize_many(text_list, lang)
    sent_stats_list = extract_sentence_stats_many(text_list, lang)

    vocab = build_global_vocab(text_list, lang, tokenized=token_list)
    fvs = {}
    for label, text, toks, sst in zip(
            labels, text_list, token_list, sent_stats_list):
        seg = SegmentInfo(
            text=text, segment_index=0, char_count=len(text), lang=lang
        )
        fvs[label] = extract_features(seg, vocab, tokens=toks, sent_stats=sst)
    return labels, group_of, fvs


# =============================================================================
# Per-variant evaluation
# =============================================================================


def _mean_std(values: List[float]) -> Tuple[float, float]:
    """Return (mean, sample std) — same convention as run_experiment."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, math.sqrt(var)


def evaluate_variant(
    labels: List[str],
    group_of: Dict[str, str],
    fvs: Dict[str, object],
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, object]:
    """Evaluate one weight vector on an extracted corpus.

    Pairwise weighted-cosine similarities become distances (1 - sim);
    the distance matrix feeds the signal competition test and 1-NN LOO
    classification from ``experiments.group_metrics``.

    :param labels: sample labels
    :param group_of: ``{label: group}``
    :param fvs: ``{label: FeatureVector}`` from ``extract_corpus_features``
    :param weights: dimension weights; None = FEATURE_WEIGHTS (default,
        reproduces run_experiment's fingerprint numbers exactly)
    :return: ``{"within", "between", "d", "competition_wins",
                "competition_pairs", "knn_acc", "knn_baseline"}``
    """
    n = len(labels)
    matrix = [[0.0] * n for _ in range(n)]
    same_sims: List[float] = []
    cross_sims: List[float] = []
    for i in range(n):
        for j in range(i + 1, n):
            sim = weighted_cosine_similarity(
                fvs[labels[i]], fvs[labels[j]], weights)
            matrix[i][j] = matrix[j][i] = 1.0 - sim
            if group_of[labels[i]] == group_of[labels[j]]:
                same_sims.append(sim)
            else:
                cross_sims.append(sim)

    same_mean, same_std = _mean_std(same_sims)
    cross_mean, cross_std = _mean_std(cross_sims)
    d_val = cohens_d(same_mean, cross_mean, same_std, cross_std,
                     len(same_sims), len(cross_sims))

    sc = signal_competition(labels, matrix, group_of)
    nn = nearest_neighbor_loo(labels, matrix, group_of)

    return {
        # Distances: within = 1 - same-translator mean similarity, etc.
        "within": 1.0 - same_mean,
        "between": 1.0 - cross_mean,
        "d": d_val,
        "competition_wins": sc["wins_original"],
        "competition_pairs": len(sc["pairs"]),
        "knn_acc": nn["accuracy"],
        "knn_baseline": nn["baseline"],
    }


# =============================================================================
# Driver: variants x scales -> CSV + report section
# =============================================================================


def run_sensitivity(
    scale_inputs: Dict[str, Path],
    scheme: str = "default",
    out_dir: Optional[Path] = None,
    lang: str = "en",
    report_path: Optional[Path] = None,
    progress_callback=None,
) -> List[Dict[str, object]]:
    """Run all variants of ``scheme`` over every scale and write the CSV.

    :param scale_inputs: ``{scale_label: grouped_input_dir}`` (insertion
        order is preserved in the output). Two scale labels resolving to
        the same directory are rejected — that would silently produce
        identical rows for different scales.
    :param scheme: one of ``SCHEMES``
    :param out_dir: directory for ``weight_sensitivity.csv``; None skips
        writing the CSV (library use)
    :param lang: sample language for fingerprint features
    :param report_path: optional report.md to append the
        "Weight sensitivity" section to (pure append; existing content
        is never modified)
    :param progress_callback: optional ``callback(current, total, stage)``
    :return: list of row dicts (CSV_COLUMNS plus ``competition_pairs``)
    """
    variants = variants_for_scheme(scheme)

    # Guard: distinct scale labels must point at distinct directories,
    # otherwise every variant would report byte-identical rows across
    # "scales" (the v2.3.0 batch bug).
    seen_dirs: Dict[Path, str] = {}
    for scale, input_dir in scale_inputs.items():
        resolved = Path(input_dir).resolve()
        if resolved in seen_dirs:
            raise ValueError(
                f"scales '{seen_dirs[resolved]}' and '{scale}' point at "
                f"the same directory: {resolved}")
        seen_dirs[resolved] = scale

    rows: List[Dict[str, object]] = []
    total = len(scale_inputs) * len(variants)
    done = 0
    for scale, input_dir in scale_inputs.items():
        labels, group_of, fvs = extract_corpus_features(Path(input_dir), lang)
        for name, weights in variants:
            metrics = evaluate_variant(labels, group_of, fvs, weights)
            rows.append({"variant": name, "scale": scale, **metrics})
            done += 1
            if progress_callback is not None:
                progress_callback(done, total, "权重敏感性")

    if out_dir is not None:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        csv_path = out_dir / "weight_sensitivity.csv"
        with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_COLUMNS)
            for row in rows:
                writer.writerow([
                    row["variant"], row["scale"],
                    f"{row['within']:.6f}", f"{row['between']:.6f}",
                    f"{row['d']:.6f}", row["competition_wins"],
                    f"{row['knn_acc']:.6f}", f"{row['knn_baseline']:.6f}",
                ])
        print(f"Weight sensitivity table written: {csv_path} "
              f"({len(rows)} rows)")

    if report_path is not None:
        append_report_section(Path(report_path), rows, scheme)
        print(f"Weight sensitivity section appended: {report_path}")

    return rows


def append_report_section(
    report_path: Path,
    rows: List[Dict[str, object]],
    scheme: str,
) -> None:
    """Append a "Weight sensitivity" section to report.md (pure append).

    One summary table (per scale: d range, original-signal wins range,
    1-NN accuracy range, majority baseline) plus a one-sentence
    conclusion. The existing report content is left untouched.
    """
    scales: List[str] = []
    for row in rows:
        if row["scale"] not in scales:
            scales.append(row["scale"])
    n_variants = len({row["variant"] for row in rows})

    lines = [
        "",
        "## Weight sensitivity",
        "",
        f"- Scheme: `{scheme}` — {n_variants} weight variant(s) x "
        f"{len(scales)} scale(s) ({', '.join(scales)}); "
        f"long table: `weight_sensitivity.csv` "
        f"(columns: {', '.join(CSV_COLUMNS)}).",
        "- The headline Burrows' Delta pipeline (`run_delta.py`: Delta "
        "matrix, Delta-based signal competition and dendrogram) never "
        "reads the fingerprint weight configuration, so the headline "
        "results are decoupled from these weights by construction; only "
        "the fingerprint-derived metrics below vary with the weights.",
        "",
        "| Scale | Variants | Cohen's d (min) | Cohen's d (max) | "
        "Original-signal wins (min–max/pairs) | 1-NN acc (min) | "
        "1-NN acc (max) | Majority baseline |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    all_d: List[float] = []
    all_win_min = None
    all_win_max = None
    all_pairs = 0
    for scale in scales:
        srows = [r for r in rows if r["scale"] == scale]
        ds = [r["d"] for r in srows]
        wins = [r["competition_wins"] for r in srows]
        accs = [r["knn_acc"] for r in srows]
        pairs = max((r["competition_pairs"] for r in srows), default=0)
        baseline = srows[0]["knn_baseline"]
        all_d.extend(ds)
        all_pairs = max(all_pairs, pairs)
        all_win_min = min(wins) if all_win_min is None else min(all_win_min, min(wins))
        all_win_max = max(wins) if all_win_max is None else max(all_win_max, max(wins))
        lines.append(
            f"| {scale} | {len(srows)} | {min(ds):.3f} | {max(ds):.3f} | "
            f"{min(wins)}–{max(wins)}/{pairs} | {min(accs):.4f} | "
            f"{max(accs):.4f} | {baseline:.4f} |"
        )

    d_min, d_max = min(all_d), max(all_d)
    stable = d_min > 0 and (all_win_min or 0) > all_pairs / 2
    if stable:
        conclusion = (
            f"Across all {n_variants} weight variant(s) x {len(scales)} "
            f"scale(s), Cohen's d stays positive "
            f"({d_min:.3f} to {d_max:.3f}) and the original-text signal "
            f"wins {all_win_min}–{all_win_max} of {all_pairs} paired "
            f"works: both qualitative conclusions are unchanged under "
            f"every variant, so they do not depend on the heuristic "
            f"fingerprint weights."
        )
    else:
        conclusion = (
            f"Across all {n_variants} weight variant(s) x {len(scales)} "
            f"scale(s), Cohen's d ranges from {d_min:.3f} to "
            f"{d_max:.3f} and original-signal wins range from "
            f"{all_win_min} to {all_win_max} of {all_pairs} paired "
            f"works; not every variant preserves the default-weight "
            f"conclusions — inspect `weight_sensitivity.csv` for the "
            f"affected variants."
        )

    lines += ["", conclusion, ""]

    with report_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))


# =============================================================================
# CLI
# =============================================================================


def _parse_scale_arg(arg: str) -> Tuple[str, Path]:
    """Parse one ``--scale NAME=DIR`` argument."""
    if "=" not in arg:
        raise argparse.ArgumentTypeError(
            f"--scale expects NAME=DIR, got: {arg!r}")
    name, _, path = arg.partition("=")
    name = name.strip()
    if not name:
        raise argparse.ArgumentTypeError(
            f"--scale expects a non-empty name: {arg!r}")
    return name, Path(path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Weight sensitivity analysis for the composite "
                    "fingerprint: rerun group-level metrics under "
                    "alternative dimension weights"
    )
    parser.add_argument(
        "--scale", action="append", required=True, metavar="NAME=DIR",
        help="one grouped input directory per scale, e.g. "
             "--scale 1k=corpus_sliced_1000 (repeatable; each DIR follows "
             "the run_experiment.py input layout: one subdirectory per "
             "group; scale names must map to distinct directories)")
    parser.add_argument(
        "--weights", default="all", choices=SCHEMES,
        help="weight scheme: all (every family, 38 variants; the default), "
             "default (existing weights, identical to no switch), uniform "
             "(1/8 each), lodo (leave-one-dimension-out, 8 variants), "
             "single (one dimension at a time, 8 variants), "
             "random (perturb within [0.5w, 1.5w], 20 seeds from "
             f"{RANDOM_BASE_SEED})")
    parser.add_argument("--out", required=True,
                        help="output directory for weight_sensitivity.csv")
    parser.add_argument("--report", default=None,
                        help="optional report.md to append the "
                             "'Weight sensitivity' section to (pure "
                             "append; existing content is never modified)")
    parser.add_argument("--lang", default="en", choices=["en", "zh"],
                        help="sample language for fingerprint features "
                             "(default en)")
    args = parser.parse_args()

    scale_inputs: Dict[str, Path] = {}
    for raw in args.scale:
        try:
            name, path = _parse_scale_arg(raw)
        except argparse.ArgumentTypeError as e:
            print(f"error: {e}", file=sys.stderr)
            sys.exit(1)
        if not path.is_dir():
            print(f"error: input directory not found: {path}",
                  file=sys.stderr)
            sys.exit(1)
        scale_inputs[name] = path

    report_path = Path(args.report) if args.report else None
    if report_path is not None and not report_path.is_file():
        print(f"error: report file not found: {report_path}",
              file=sys.stderr)
        sys.exit(1)

    try:
        rows = run_sensitivity(
            scale_inputs, scheme=args.weights, out_dir=Path(args.out),
            lang=args.lang, report_path=report_path,
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Done: {len(rows)} variant x scale row(s) "
          f"(scheme={args.weights}).")


if __name__ == "__main__":
    main()
