"""Export dendrograms under four linkage rules (release artifact).

The main pipeline (``core.stylometry.hierarchical_cluster``) is fixed to
average linkage. For the paper's linkage-robustness appendix this script
re-clusters the released chunk-level Delta matrices
(``data/delta_matrix_{1k,2k,4k}.csv``) under average / complete / Ward /
single linkage and renders one dendrogram PNG per scale x linkage with
the existing ``viz.dendrogram.plot_dendrogram`` renderer.

Clustering is pure Python and deterministic: at each step the pair of
clusters with the smallest inter-cluster distance is merged; ties are
broken by scan order (same convention as
``core.stylometry.hierarchical_cluster``). Inter-cluster distance:

- single:   min over cross-cluster pairs
- complete: max over cross-cluster pairs
- average:  mean over cross-cluster pairs (UPGMA, the pipeline default)
- ward:     Ward's minimum-variance criterion via the Lance-Williams
            update on squared distances (Ward.D2, the R default since
            3.1): with h = d^2,
            h(u,k) = ((n_i+n_k) h(i,k) + (n_j+n_k) h(j,k)
                      - n_k h(i,j)) / (n_i+n_j+n_k);
            merge heights are plotted as sqrt(h), back on the Delta
            scale. Ward cannot be recomputed from member-pair
            distances, so it keeps its own cluster-distance table.

Validation: before writing anything, the script counts *exact story
subtrees* in each 4k dendrogram — a story counts when its full chunk
set appears as the leaf set of some node in the tree (16 stories at
4k) — and asserts the paper's reference counts: average 9/16,
complete 10/16, ward 10/16, single 5/16. On any mismatch it stops
without writing.

Output: ``results/dendrograms/{scale}_{linkage}.png`` (12 files).

Usage:
    python scripts/export_linkage_dendrograms.py
"""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path
from typing import Dict, FrozenSet, List, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from viz.dendrogram import plot_dendrogram  # noqa: E402

SCALES = ("1k", "2k", "4k")
LINKAGES = ("average", "complete", "ward", "single")

N_STORIES_4K = 16
# 论文参考值：4k 树状图中精确故事子树数（整篇切片恰好构成一个子树）
REF_EXACT_4K = {"average": 9, "complete": 10, "ward": 10, "single": 5}


def load_delta_matrix(path: Path) -> Tuple[List[str], List[List[float]]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    labels = rows[0][1:]
    matrix = [[float(x) for x in row[1:]] for row in rows[1:]]
    return labels, matrix


def _story(label: str) -> str:
    return label.split("/", 1)[1].rsplit("__chunk", 1)[0]


def exact_story_count(tree: Dict[str, object], labels: List[str]) -> int:
    """精确故事子树数：整篇切片恰好等于某节点叶集合的故事数。"""
    chunks: Dict[str, Set[str]] = {}
    for la in labels:
        chunks.setdefault(_story(la), set()).add(la)
    story_sets = {frozenset(v) for v in chunks.values()}

    node_leaf_sets: Set[FrozenSet[str]] = set()

    def collect(node: Dict[str, object]) -> FrozenSet[str]:
        if node["left"] is None and node["right"] is None:
            return frozenset([str(node["label"])])
        left: Dict[str, object] = node["left"]  # type: ignore[assignment]
        right: Dict[str, object] = node["right"]  # type: ignore[assignment]
        s = collect(left) | collect(right)
        node_leaf_sets.add(s)
        return s

    collect(tree)
    return len(story_sets & node_leaf_sets)


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
    matrix: List[List[float]], labels: List[str], linkage: str,
) -> Dict[str, object]:
    """Agglomerative clustering for single/complete/average linkage.

    Same node/tie conventions as ``core.stylometry.hierarchical_cluster``
    but a selectable linkage.
    """
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


def hierarchical_cluster_ward(
    matrix: List[List[float]], labels: List[str],
) -> Dict[str, object]:
    """Ward 联结（Ward.D2）：Lance-Williams 更新，纯 Python，确定性。

    Ward 距离不能由簇成员的两两原始距离重算，必须维护簇间距离表：
    以 h = d^2 存储，合并规则
    ``h(u,k) = ((n_i+n_k) h(i,k) + (n_j+n_k) h(j,k) - n_k h(i,j))
               / (n_i+n_j+n_k)``，
    节点绘制高度取 sqrt(h)，回到 Delta 尺度。nodes/members/sizes 均按
    簇 id 追加索引，只增不删。
    """
    n = len(labels)
    nodes: List[Dict[str, object]] = [
        {"label": la, "height": 0.0, "left": None, "right": None}
        for la in labels
    ]
    members: List[List[int]] = [[i] for i in range(n)]
    sizes: List[int] = [1] * n
    active: List[int] = list(range(n))
    # 簇间 Ward 距离表，键为 (小 id, 大 id)，值为 h = d^2
    h: Dict[Tuple[int, int], float] = {}
    for i in range(n):
        for j in range(i + 1, n):
            h[(i, j)] = matrix[i][j] ** 2
    next_id = n

    def _h(a: int, b: int) -> float:
        return h[(a, b) if a < b else (b, a)]

    while len(active) > 1:
        best = None  # (h, pos_a, pos_b)
        for a in range(len(active)):
            for b in range(a + 1, len(active)):
                d = _h(active[a], active[b])
                if best is None or d < best[0]:  # 并列保留先扫到的一对
                    best = (d, a, b)
        assert best is not None
        d_ij, pa, pb = best
        ci, cj = active[pa], active[pb]
        ni, nj = sizes[ci], sizes[cj]

        cu = next_id
        next_id += 1
        for ck in active:
            if ck in (ci, cj):
                continue
            nk = sizes[ck]
            h_uk = ((ni + nk) * _h(ci, ck) + (nj + nk) * _h(cj, ck)
                    - nk * d_ij) / (ni + nj + nk)
            h[(min(cu, ck), max(cu, ck))] = max(h_uk, 0.0)

        merged = {
            "label": None,
            "height": math.sqrt(max(d_ij, 0.0)),
            "left": nodes[ci],
            "right": nodes[cj],
        }
        nodes.append(merged)
        members.append(members[ci] + members[cj])
        sizes.append(ni + nj)
        # 删除旧簇（先大后小避免位移）
        for pos in sorted((pa, pb), reverse=True):
            del active[pos]
        active.append(cu)
    return nodes[-1]


def cluster(
    matrix: List[List[float]], labels: List[str], linkage: str,
) -> Dict[str, object]:
    if linkage == "ward":
        return hierarchical_cluster_ward(matrix, labels)
    return hierarchical_cluster(matrix, labels, linkage)


def main() -> None:
    out_dir = ROOT / "results" / "dendrograms"
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- 4k 参考值校验：任何一项对不上，停止且不写任何文件 ---
    labels_4k, matrix_4k = load_delta_matrix(
        ROOT / "data" / "delta_matrix_4k.csv"
    )
    for linkage in LINKAGES:
        tree = cluster(matrix_4k, labels_4k, linkage)
        exact = exact_story_count(tree, labels_4k)
        print(f"[4k] {linkage:8s} exact story subtrees: "
              f"{exact}/{N_STORIES_4K} (paper ref {REF_EXACT_4K[linkage]})")
        if exact != REF_EXACT_4K[linkage]:
            print(f"ERROR: 4k {linkage} exact-story count {exact} != "
                  f"reference {REF_EXACT_4K[linkage]}; nothing written.",
                  file=sys.stderr)
            sys.exit(1)
    print("4k exact-story reference counts: all matched.")

    for scale in SCALES:
        labels, matrix = load_delta_matrix(
            ROOT / "data" / f"delta_matrix_{scale}.csv"
        )
        for linkage in LINKAGES:
            out = out_dir / f"dendrogram_{scale}_{linkage}.png"
            if out.exists():
                print(f"kept:  {out} (already exported)")
                continue
            tree = cluster(matrix, labels, linkage)
            plot_dendrogram(
                tree, out,
                title=f"Burrows' Delta Hierarchical Clustering "
                      f"({scale}, {linkage} linkage)",
            )
            print(f"saved: {out}")


if __name__ == "__main__":
    main()
