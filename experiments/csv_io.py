"""Shared CSV writers for experiment artifacts.

Byte format is fixed across all callers: UTF-8 BOM (``utf-8-sig``),
``newline=""`` and 6-decimal floats — identical to the historical inline
copies in ``run_delta.py`` / ``run_experiment.py`` /
``export_paper_data.py``, so existing outputs stay byte-identical.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, List, Tuple


def write_delta_csv(path: Path, labels: List[str],
                    matrix: List[List[float]]) -> None:
    """Delta distance matrix: empty corner cell, 6-decimal distances."""
    with Path(path).open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([""] + labels)
        for label, row in zip(labels, matrix):
            writer.writerow([label] + [f"{d:.6f}" for d in row])


def write_nn_predictions_csv(path: Path,
                             predictions: Iterable[dict]) -> None:
    """1-NN leave-one-out predictions (hit rendered as ``"1"``/``"0"``)."""
    with Path(path).open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["sample", "true_group", "nn_sample", "nn_group", "hit"])
        for p in predictions:
            writer.writerow([p["sample"], p["true_group"], p["nn_sample"],
                             p["nn_group"], "1" if p["hit"] else "0"])


def write_signal_competition_csv(path: Path, pairs: Iterable[dict]) -> None:
    """Signal competition pairs with 6-decimal distances."""
    with Path(path).open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["work", "group_a", "group_b",
                         "cross_translator_dist", "same_translator_dist",
                         "winner"])
        for row in pairs:
            writer.writerow([row["work"], row["group_a"], row["group_b"],
                             f"{row['cross_translator_dist']:.6f}",
                             f"{row['same_translator_dist']:.6f}",
                             row["winner"]])


def write_fingerprint_pairs_csv(
        path: Path, rows: Iterable[Tuple[str, str, str, float]]) -> None:
    """Pairwise fingerprint similarities.

    :param rows: ``(sample_a, sample_b, pair_type, similarity)`` tuples in
        the caller's iteration order
    """
    with Path(path).open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["sample_a", "sample_b", "pair_type", "similarity"])
        for la, lb, ptype, sim in rows:
            writer.writerow([la, lb, ptype, f"{sim:.6f}"])
