"""Post-hoc analyses for the v9 study revision (no pipeline changes).

Two analyses over the released chunk-level data, both with all
"same-story" pairs removed or tabulated:

Task 1 — aggregate metrics after excluding same-story pairs
    (a) Fingerprint track: Cohen's d of same-translator vs
        cross-translator pairwise similarity (pooled SD, same formula as
        ``core.linguistic_fingerprint.cohens_d`` with sample-size
        weighting), computed only on cross-story pairs.
    (b) Delta track: within-translator / between-translator mean Delta
        and their ratio, computed only on cross-story pairs.

Task 2 — nearest-neighbour structure of the Delta matrices
    For each chunk, its nearest neighbour (self excluded, ties broken by
    label order as in ``experiments.group_metrics.nearest_neighbor_loo``):
      (i)   share whose NN is the same story in the *other* translation;
      (ii)  share whose NN is the same story in *any* translation;
      plus the plain 1-NN translator accuracy.

Inputs (all already in the repo):
    data/delta_matrix_{1k,2k,4k}.csv          chunk-level Delta matrices
    results/tokenizer_control/<scale>/fingerprint_pairs.csv
        pairwise fingerprint similarities. The fingerprint leg is
        tokenizer-independent (``export_paper_data.py`` docstring), and
        these files are byte-identical to the main run's pairs, so they
        serve as the main-analysis fingerprint pairs.

Outputs:
    results/same_story_exclusion_d.csv
    results/nn_structure_proportions.csv

Validation: the script asserts the hand-computed 4k reference values
(Delta within 1.064 / between 1.178 / ratio 1.11; NN 26/46, 33/46,
20/46) before writing anything.

Usage:
    python scripts/posthoc_v9.py
"""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
SCALES = ("1k", "2k", "4k")

# Hand-computed 4k reference values (verified by the authors).
REF_DELTA_4K = dict(within=1.064, between=1.178, ratio=1.11)
REF_NN_4K = dict(n=46, same_story_other=26, same_story_any=33, nn_hits=20)


def parse_label(label: str) -> Tuple[str, str]:
    """``译者/故事__chunkNNN`` -> (translator, story)."""
    translator, rest = label.split("/", 1)
    story = rest.rsplit("__chunk", 1)[0]
    return translator, story


def load_delta_matrix(path: Path) -> Tuple[List[str], List[List[float]]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    labels = rows[0][1:]
    matrix = [[float(x) for x in row[1:]] for row in rows[1:]]
    assert len(labels) == len(matrix) and all(
        len(r) == len(labels) for r in matrix
    ), f"ragged delta matrix: {path}"
    return labels, matrix


# =============================================================================
# Task 1
# =============================================================================


def cohens_d_pooled(a: List[float], b: List[float]) -> float:
    """(mean_a - mean_b) / pooled SD, sample-size weighted — the same
    formula as ``core.linguistic_fingerprint.cohens_d`` with n_a, n_b > 1.
    """
    n_a, n_b = len(a), len(b)
    mean_a = sum(a) / n_a
    mean_b = sum(b) / n_b
    var_a = sum((x - mean_a) ** 2 for x in a) / (n_a - 1)
    var_b = sum((x - mean_b) ** 2 for x in b) / (n_b - 1)
    pooled_var = ((n_a - 1) * var_a + (n_b - 1) * var_b) / (n_a + n_b - 2)
    return (mean_a - mean_b) / math.sqrt(pooled_var)


def fingerprint_d_excl_same_story(scale: str) -> float:
    """Cohen's d (same- vs cross-translator similarity) on cross-story
    pairs only."""
    path = ROOT / "results" / "tokenizer_control" / scale / "fingerprint_pairs.csv"
    same: List[float] = []
    cross: List[float] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            _, story_a = parse_label(row["sample_a"])
            _, story_b = parse_label(row["sample_b"])
            if story_a == story_b:
                continue  # 剔除同故事对（within 侧与 between 侧都剔）
            (same if row["pair_type"] == "same" else cross).append(
                float(row["similarity"])
            )
    assert same and cross, f"no pairs left after exclusion: {scale}"
    return cohens_d_pooled(same, cross)


def delta_within_between_excl_same_story(
    labels: List[str], matrix: List[List[float]]
) -> Tuple[float, float, float]:
    """Within/between mean Delta on cross-story pairs only, and ratio."""
    meta = [parse_label(la) for la in labels]
    within: List[float] = []
    between: List[float] = []
    n = len(labels)
    for i in range(n):
        t_i, s_i = meta[i]
        for j in range(i + 1, n):
            t_j, s_j = meta[j]
            if s_i == s_j:
                continue  # 同故事对：两侧都剔除
            (within if t_i == t_j else between).append(matrix[i][j])
    w = sum(within) / len(within)
    b = sum(between) / len(between)
    return w, b, b / w


# =============================================================================
# Task 2
# =============================================================================


def nn_structure(
    labels: List[str], matrix: List[List[float]]
) -> Dict[str, float]:
    """Nearest-neighbour structure proportions of a Delta matrix."""
    meta = [parse_label(la) for la in labels]
    n = len(labels)
    n_same_story_other = 0
    n_same_story_any = 0
    n_hits = 0
    for i in range(n):
        best_j, best_d = -1, math.inf
        for j in range(n):
            if j == i:
                continue
            if matrix[i][j] < best_d:  # 并列时保留标签序先到者
                best_d = matrix[i][j]
                best_j = j
        t_i, s_i = meta[i]
        t_j, s_j = meta[best_j]
        if s_i == s_j:
            n_same_story_any += 1
            if t_i != t_j:
                n_same_story_other += 1
        if t_i == t_j:
            n_hits += 1
    return {
        "n": n,
        "same_story_other": n_same_story_other,
        "same_story_any": n_same_story_any,
        "hits": n_hits,
        "nn_same_story_other_trans": n_same_story_other / n,
        "nn_same_story_any": n_same_story_any / n,
        "knn_acc": n_hits / n,
    }


# =============================================================================
# Main
# =============================================================================


def main() -> None:
    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)

    task1_rows = []
    task2_rows = []
    for scale in SCALES:
        labels, matrix = load_delta_matrix(
            ROOT / "data" / f"delta_matrix_{scale}.csv"
        )
        d = fingerprint_d_excl_same_story(scale)
        w, b, ratio = delta_within_between_excl_same_story(labels, matrix)
        task1_rows.append((scale, d, w, b, ratio))

        nn = nn_structure(labels, matrix)
        task2_rows.append((scale, nn))

        print(
            f"[{scale}] d={d:.4f}  within={w:.4f} between={b:.4f} "
            f"ratio={ratio:.4f} | NN other-trans={nn['same_story_other']}"
            f"/{nn['n']} any-trans={nn['same_story_any']}/{nn['n']} "
            f"hits={nn['hits']}/{nn['n']}"
        )

    # --- 4k 参考值校验（手算已验证；对不上就不写文件） ---
    d4, w4, b4, r4 = task1_rows[SCALES.index("4k")][1:]
    assert abs(w4 - REF_DELTA_4K["within"]) < 5e-4, f"4k within {w4:.4f}"
    assert abs(b4 - REF_DELTA_4K["between"]) < 5e-4, f"4k between {b4:.4f}"
    assert abs(r4 - REF_DELTA_4K["ratio"]) < 5e-3, f"4k ratio {r4:.4f}"
    nn4 = task2_rows[SCALES.index("4k")][1]
    assert nn4["n"] == REF_NN_4K["n"]
    assert nn4["same_story_other"] == REF_NN_4K["same_story_other"]
    assert nn4["same_story_any"] == REF_NN_4K["same_story_any"]
    assert nn4["hits"] == REF_NN_4K["nn_hits"]
    print("4k reference values: all matched.")

    p1 = out_dir / "same_story_exclusion_d.csv"
    with p1.open("w", encoding="utf-8-sig", newline="") as f:
        wr = csv.writer(f)
        wr.writerow([
            "scale", "d_excl_same_story", "delta_within_excl",
            "delta_between_excl", "delta_ratio_excl",
        ])
        for scale, d, w, b, ratio in task1_rows:
            wr.writerow([scale, f"{d:.6f}", f"{w:.6f}", f"{b:.6f}",
                         f"{ratio:.6f}"])
    print(f"written: {p1}")

    p2 = out_dir / "nn_structure_proportions.csv"
    with p2.open("w", encoding="utf-8-sig", newline="") as f:
        wr = csv.writer(f)
        wr.writerow([
            "scale", "n_chunks", "nn_same_story_other_trans",
            "nn_same_story_any", "knn_acc",
        ])
        for scale, nn in task2_rows:
            wr.writerow([
                scale, nn["n"], f"{nn['nn_same_story_other_trans']:.6f}",
                f"{nn['nn_same_story_any']:.6f}", f"{nn['knn_acc']:.6f}",
            ])
    print(f"written: {p2}")


if __name__ == "__main__":
    sys.exit(main())
