"""Paper data export utilities (v2.3.1) — data export only, no algorithm
changes.

Driven from one corpus root (one subdirectory per group, full unsliced
``.txt`` files), this script produces four export sets:

1. ``mfw100.txt`` — the 100 most frequent words fitted on the *merged*
   corpus: all works of all groups pooled (full texts, unsliced),
   tokenized with the stylometry tokenizer (``[A-Za-z]+``, lowercased),
   ranked by count descending with alphabetical tie-break, one word per
   line. This is the same fit ``build_freq_table`` performs internally.

2. ``delta_matrix_1k.csv`` / ``delta_matrix_2k.csv`` — chunk-level
   Burrows' Delta matrices at the 1k/2k scales (chunks are cut with
   ``slice_corpus``; the 100 MFW features are refit per scale on the
   chunks, exactly as ``run_experiment.py`` does). CSV format is
   byte-compatible with ``run_delta.py`` output (UTF-8 BOM, empty corner
   cell, 6 decimals), matching the existing ``delta_matrix_4k.csv``.

3. ``feature_scores.csv`` — per chunk x per scale (1k/2k/4k), the eight
   per-dimension scores of the composite fingerprint: the chunk's
   per-dimension similarity to its own group's centroid (the components
   of ``weighted_cosine_similarity``, before weighting), plus the
   weighted total under the default weights.

4. Tokenizer control run — the full Delta pipeline rerun with the
   tokenizer changed to ``[A-Za-z']+`` (contractions kept), at all three
   scales, writing CSVs only (delta_matrix / nn_predictions /
   signal_competition / fingerprint_pairs) under
   ``results/tokenizer_control/<scale>/``. The fingerprint leg uses
   ``core.analyzer`` tokenization and is therefore unaffected by this
   control; it is included only for completeness of the pipeline rerun.
   Control results are not meant for the paper's main tables.

Usage:
    python experiments/export_paper_data.py --input corpus \
        --data-out data --control-out results/tokenizer_control
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Allow running directly from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.stylometry import (  # noqa: E402
    build_freq_table,
    zscore,
    delta_matrix,
)
from experiments.slice_corpus import slice_corpus  # noqa: E402
from experiments.csv_io import (  # noqa: E402
    write_delta_csv,
    write_fingerprint_pairs_csv,
    write_nn_predictions_csv,
    write_signal_competition_csv,
)

__all__ = [
    "CONTROL_TOKEN_RE",
    "control_tokenize",
    "export_mfw",
    "export_delta_matrices",
    "export_feature_scores",
    "run_tokenizer_control",
]

DELTA_SCALES = (1000, 2000)
FEATURE_SCALES = (1000, 2000, 4000)

# Tokenizer for the control run: same as core.stylometry but keeps
# apostrophes, so contractions (don't, it's) survive as single tokens.
CONTROL_TOKEN_RE = re.compile(r"[A-Za-z']+")


def control_tokenize(text: str) -> List[str]:
    """Control-run tokenizer: ``[A-Za-z']+``, lowercased."""
    return [m.group(0).lower() for m in CONTROL_TOKEN_RE.finditer(text)]


def _scale_label(size: int) -> str:
    """1500 -> '1.5k', 2000 -> '2k'."""
    return f"{size / 1000:g}k"


def _load_corpus(input_dir: Path) -> Dict[str, Dict[str, str]]:
    """Lazy wrapper around run_experiment.load_groups (pulls matplotlib)."""
    from experiments.run_experiment import load_groups

    return load_groups(Path(input_dir))


def _slice_groups(input_dir: Path, out_dir: Path, chunk_size: int) -> int:
    """Slice each first-level group directory separately.

    ``slice_corpus`` searches recursively; slicing the corpus root as a
    whole would also re-slice stray outputs left inside it (e.g. a
    previous ``weight_sensitivity/sliced_*``). Slicing per group keeps
    the export sources limited to the actual works.

    :return: total number of chunks written
    """
    total = 0
    for sub in sorted(p for p in Path(input_dir).iterdir() if p.is_dir()):
        if not list(sub.glob("*.txt")):
            continue  # 非组目录（无直接 .txt），跳过
        total += len(slice_corpus(sub, Path(out_dir) / sub.name,
                                  chunk_size))
    return total


def _flatten(groups: Dict[str, Dict[str, str]]) -> Tuple[
        Dict[str, str], Dict[str, str]]:
    """{group: {label: text}} -> (texts, group_of), labels in load order."""
    texts: Dict[str, str] = {}
    group_of: Dict[str, str] = {}
    for gname, samples in groups.items():
        for label, text in samples.items():
            texts[label] = text
            group_of[label] = gname
    return texts, group_of


# =============================================================================
# 1. MFW wordlist (merged fit)
# =============================================================================


def export_mfw(input_dir: Path, out_path: Path, top_n: int = 100
               ) -> List[str]:
    """Fit the top-N MFW on the merged corpus and write one word per line.

    Merge convention: every full unsliced text of every group is pooled;
    the stylometry tokenizer (``[A-Za-z]+``, lowercase) counts tokens;
    words are ranked by count descending, ties broken alphabetically —
    identical to the feature selection inside ``build_freq_table``.

    :return: the exported word list
    """
    groups = _load_corpus(Path(input_dir))
    texts, _ = _flatten(groups)
    features = build_freq_table(texts, n=top_n)["features"]

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(features) + "\n", encoding="utf-8")
    print(f"MFW wordlist written: {out_path} ({len(features)} words, "
          f"merged fit over {len(texts)} full texts)")
    return features  # type: ignore[return-value]


# =============================================================================
# 2. Chunk-level Delta matrices at the 1k/2k scales
# =============================================================================


def export_delta_matrices(input_dir: Path, out_dir: Path,
                          scales: Tuple[int, ...] = DELTA_SCALES,
                          top_n: int = 100) -> List[Path]:
    """Slice the corpus and write ``delta_matrix_{label}.csv`` per scale.

    The 100 MFW features are refit per scale on the chunks (the
    ``run_experiment.py`` convention), so the matrices are directly
    comparable to the existing ``delta_matrix_4k.csv``.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    with tempfile.TemporaryDirectory() as td:
        for size in scales:
            label = _scale_label(size)
            sliced = Path(td) / f"sliced_{size}"
            n_chunks = _slice_groups(Path(input_dir), sliced, size)
            groups = _load_corpus(sliced)
            texts, _ = _flatten(groups)
            ft = build_freq_table(texts, n=top_n)
            zs = zscore(ft)
            dm = delta_matrix(zs)
            out_path = out_dir / f"delta_matrix_{label}.csv"
            write_delta_csv(out_path, dm["labels"], dm["matrix"])  # type: ignore[arg-type]
            written.append(out_path)
            print(f"Delta matrix ({label}, {n_chunks} chunks, "
                  f"top-{top_n}): {out_path}")
    return written


# =============================================================================
# 3. Per-chunk x per-scale fingerprint dimension scores
# =============================================================================


def export_feature_scores(input_dir: Path, out_path: Path,
                          scales: Tuple[int, ...] = FEATURE_SCALES,
                          lang: str = "en") -> Path:
    """Write ``feature_scores.csv``: one row per chunk x scale.

    Columns: scale, sample, group, the eight per-dimension scores
    (``core.linguistic_fingerprint.dimension_scores`` of the chunk
    against its own group's centroid) and ``weighted_total`` (the default
    weighted-cosine composite, equal to the sum of weight x score).
    """
    from core.linguistic_fingerprint import (
        FEATURE_WEIGHTS,
        _build_aggregate_feature_vector,
        dimension_scores,
        weighted_cosine_similarity,
    )
    from experiments.weight_sensitivity import extract_corpus_features

    dims = list(FEATURE_WEIGHTS)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n_rows = 0
    with tempfile.TemporaryDirectory() as td:
        with out_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["scale", "sample", "group"] + dims
                            + ["weighted_total"])
            for size in scales:
                label = _scale_label(size)
                sliced = Path(td) / f"sliced_{size}"
                _slice_groups(Path(input_dir), sliced, size)
                labels, group_of, fvs = extract_corpus_features(
                    sliced, lang)
                members: Dict[str, List[str]] = {}
                for la in labels:
                    members.setdefault(group_of[la], []).append(la)
                centroids = {
                    g: _build_aggregate_feature_vector(
                        [fvs[la] for la in las])
                    for g, las in members.items()
                }
                for la in labels:
                    scores = dimension_scores(fvs[la],
                                              centroids[group_of[la]])
                    total = weighted_cosine_similarity(
                        fvs[la], centroids[group_of[la]])
                    writer.writerow(
                        [label, la, group_of[la]]
                        + [f"{scores[d]:.6f}" for d in dims]
                        + [f"{total:.6f}"])
                    n_rows += 1
                print(f"Feature scores ({label}): {len(labels)} chunks")
    print(f"Feature score table written: {out_path} ({n_rows} rows)")
    return out_path


# =============================================================================
# 4. Tokenizer control run ([A-Za-z']+, contractions kept)
# =============================================================================


def run_tokenizer_control(input_dir: Path, out_root: Path,
                          scales: Tuple[int, ...] = FEATURE_SCALES,
                          top_n: int = 100, lang: str = "en"
                          ) -> List[Path]:
    """Rerun the full pipeline with the control tokenizer, CSVs only.

    Per scale, writes under ``out_root/<label>/``:
    ``delta_matrix.csv``, ``nn_predictions.csv``,
    ``signal_competition.csv`` (all affected by the tokenizer change)
    and ``fingerprint_pairs.csv`` (tokenizer-independent leg, included
    only so the pipeline rerun is complete).
    """
    from experiments.group_metrics import (
        nearest_neighbor_loo,
        signal_competition,
    )
    from core.linguistic_fingerprint import weighted_cosine_similarity
    from experiments.weight_sensitivity import extract_corpus_features

    written: List[Path] = []
    with tempfile.TemporaryDirectory() as td:
        for size in scales:
            label = _scale_label(size)
            sliced = Path(td) / f"sliced_{size}"
            _slice_groups(Path(input_dir), sliced, size)
            groups = _load_corpus(sliced)
            texts, group_of = _flatten(groups)
            labels = list(texts.keys())

            # (a) Delta chain with the control tokenizer
            ft = build_freq_table(texts, n=top_n,
                                  tokenize_fn=control_tokenize)
            zs = zscore(ft)
            dm = delta_matrix(zs)
            matrix: List[List[float]] = dm["matrix"]  # type: ignore[assignment]
            dm_labels: List[str] = dm["labels"]  # type: ignore[assignment]

            out_dir = Path(out_root) / label
            out_dir.mkdir(parents=True, exist_ok=True)

            csv_path = out_dir / "delta_matrix.csv"
            write_delta_csv(csv_path, dm_labels, matrix)
            written.append(csv_path)

            nn = nearest_neighbor_loo(dm_labels, matrix, group_of)
            nn_path = out_dir / "nn_predictions.csv"
            write_nn_predictions_csv(nn_path, nn["predictions"])  # type: ignore[arg-type]
            written.append(nn_path)

            sc = signal_competition(dm_labels, matrix, group_of)
            sc_path = out_dir / "signal_competition.csv"
            write_signal_competition_csv(sc_path, sc["pairs"])  # type: ignore[arg-type]
            written.append(sc_path)

            # (b) Fingerprint leg (unaffected by the control tokenizer)
            fp_labels, fp_group_of, fvs = extract_corpus_features(
                sliced, lang)
            pairs_path = out_dir / "fingerprint_pairs.csv"

            def _fp_rows():
                for i, la in enumerate(fp_labels):
                    for lb in fp_labels[i + 1:]:
                        sim = weighted_cosine_similarity(fvs[la], fvs[lb])
                        ptype = ("same" if fp_group_of[la]
                                 == fp_group_of[lb] else "cross")
                        yield la, lb, ptype, sim

            write_fingerprint_pairs_csv(pairs_path, _fp_rows())
            written.append(pairs_path)

            print(f"Tokenizer control ({label}): "
                  f"{len(labels)} chunks -> {out_dir}")
    return written


# =============================================================================
# CLI
# =============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export paper data artifacts (v2.3.1): MFW wordlist, "
                    "chunk-level Delta matrices, per-dimension fingerprint "
                    "scores, and the tokenizer control run")
    parser.add_argument("--input", required=True,
                        help="corpus root; each subdirectory is one group, "
                             "full unsliced .txt files inside")
    parser.add_argument("--data-out", default="data",
                        help="directory for mfw100.txt / delta_matrix_*.csv "
                             "/ feature_scores.csv (default: data)")
    parser.add_argument("--control-out",
                        default="results/tokenizer_control",
                        help="output root of the tokenizer control run "
                             "(default: results/tokenizer_control)")
    parser.add_argument("--top-n", type=int, default=100,
                        help="number of MFW features (default 100)")
    parser.add_argument("--lang", default="en", choices=["en", "zh"],
                        help="sample language for fingerprint features "
                             "(default en)")
    parser.add_argument("--skip-control", action="store_true",
                        help="only write the data/ exports, skip the "
                             "tokenizer control run")
    args = parser.parse_args()

    input_dir = Path(args.input)
    if not input_dir.is_dir():
        print(f"error: input directory not found: {input_dir}",
              file=sys.stderr)
        sys.exit(1)

    data_out = Path(args.data_out)
    try:
        export_mfw(input_dir, data_out / f"mfw{args.top_n}.txt",
                   top_n=args.top_n)
        export_delta_matrices(input_dir, data_out, top_n=args.top_n)
        export_feature_scores(input_dir, data_out / "feature_scores.csv",
                              lang=args.lang)
        if not args.skip_control:
            run_tokenizer_control(input_dir, Path(args.control_out),
                                  top_n=args.top_n, lang=args.lang)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    print("Done.")


if __name__ == "__main__":
    main()
