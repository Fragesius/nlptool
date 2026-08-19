"""Export dendrograms under three linkage methods (release artifact).

The main pipeline (``core.stylometry.hierarchical_cluster``) is fixed to
average linkage. For the paper's linkage-robustness appendix this script
re-clusters the released chunk-level Delta matrices
(``data/delta_matrix_{1k,2k,4k}.csv``) under single / complete / average
linkage and renders one dendrogram PNG per scale x linkage with the
existing ``viz.dendrogram.plot_dendrogram`` renderer.

Clustering is pure Python and deterministic: at each step the pair of
clusters with the smallest inter-cluster distance is merged; ties are
broken by scan order (same convention as
``core.stylometry.hierarchical_cluster``). Inter-cluster distance:

- single:   min over cross-cluster pairs
- complete: max over cross-cluster pairs
- average:  mean over cross-cluster pairs (UPGMA, the pipeline default)

Output: ``results/dendrograms/{scale}_{linkage}.png`` (9 files).

Usage:
    python scripts/export_linkage_dendrograms.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from viz.dendrogram import plot_dendrogram  # noqa: E402

SCALES = ("1k", "2k", "4k")
LINKAGES = ("single", "complete", "average")


def load_delta_matrix(path: Path) -> Tuple[List[str], List[List[float]]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    labels = rows[0][1:]
    matrix = [[float(x) for x in row[1:]] for row in rows[1:]]
    return labels, matrix


def _cluster_dist(
    members_a: List[int], members_b: List[int],
    matrix: List[List[float]], linkage: str,
) -> float:
    dists = [matrix[i][j] for i in members_a for j in members_b]
    if linkage == "single":
        return min(dists)
    if linkage == "complete":
        return max(dists)
    return sum(dists) / len(dists)  # average


def hierarchical_cluster(
    matrix: List[List[float]], labels: List[str], linkage: str
) -> Dict[str, object]:
    """Agglomerative clustering with the same node/tie conventions as
    ``core.stylometry.hierarchical_cluster`` but a selectable linkage.
    """
    # 每个活跃簇：嵌套 dict 节点 + 成员索引列表
    nodes: List[Dict[str, object]] = [
        {"label": la, "height": 0.0, "left": None, "right": None}
        for la in labels
    ]
    members: List[List[int]] = [[i] for i in range(len(labels))]

    while len(nodes) > 1:
        best = None  # (dist, i, j)
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                d = _cluster_dist(members[i], members[j], matrix, linkage)
                if best is None or d < best[0]:  # 并列保留先扫到的一对
                    best = (d, i, j)
        assert best is not None
        d, i, j = best
        merged = {
            "label": None,
            "height": d,
            "left": nodes[i],
            "right": nodes[j],
        }
        merged_members = members[i] + members[j]
        # 删除 j 再删除 i（j > i），把合并簇追加到末尾
        del nodes[j], members[j]
        del nodes[i], members[i]
        nodes.append(merged)
        members.append(merged_members)
    return nodes[0]


def main() -> None:
    out_dir = ROOT / "results" / "dendrograms"
    out_dir.mkdir(parents=True, exist_ok=True)
    for scale in SCALES:
        labels, matrix = load_delta_matrix(
            ROOT / "data" / f"delta_matrix_{scale}.csv"
        )
        for linkage in LINKAGES:
            tree = hierarchical_cluster(matrix, labels, linkage)
            out = out_dir / f"dendrogram_{scale}_{linkage}.png"
            plot_dendrogram(
                tree, out,
                title=f"Burrows' Delta Hierarchical Clustering "
                      f"({scale}, {linkage} linkage)",
            )
            print(f"saved: {out}")


if __name__ == "__main__":
    main()
