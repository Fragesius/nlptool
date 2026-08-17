"""Group-level research metrics for the translator-style experiment.

Two metrics built on top of the Burrows' Delta distance matrix
(``core.stylometry.delta_matrix`` output):

1. Leave-one-out 1-NN classification accuracy
   (``nearest_neighbor_loo``): each sample is classified by the group of
   its nearest other sample in Delta space; compared against the
   majority-group random baseline.

2. Signal competition test (``signal_competition``): for works present
   (by file stem, ``__chunkNNN`` suffix stripped) in two groups — e.g.
   two translators' renderings of the same original — compares

   a) cross-translator same-work distance (mean Delta between the work's
      chunks in group A and its chunks in group B), against
   b) same-translator cross-work distance (mean Delta between the work's
      chunks in group A and A's chunks of *other* works, and likewise
      for B, averaged).

   a < b means the original-work signal wins; a > b means the
   translator-style signal wins. Win counts are evaluated with a
   two-sided sign test (binomial, H0: p = 0.5, pure Python).

Both are pure-Python and deterministic (ties broken by label order).
"""

from __future__ import annotations

import math
import re
from itertools import combinations
from typing import Dict, List, Tuple

__all__ = [
    "nearest_neighbor_loo",
    "signal_competition",
    "sign_test_pvalue",
    "work_stem",
]

_CHUNK_SUFFIX_RE = re.compile(r"^(.*)__chunk\d+$")


def work_stem(sample_label: str) -> str:
    """切片标签（``group/stem``）→ 切片前的篇目词根。

    去掉 ``__chunkNNN`` 后缀；无后缀时词根即文件 stem。
    """
    stem = sample_label.split("/", 1)[-1]
    m = _CHUNK_SUFFIX_RE.match(stem)
    return m.group(1) if m else stem


# =============================================================================
# 1-NN 留一法分类
# =============================================================================


def nearest_neighbor_loo(
    labels: List[str], matrix: List[List[float]], group_of: Dict[str, str]
) -> Dict[str, object]:
    """基于 Delta 距离矩阵的留一法最近邻分类。

    对每个切片，找除自身外 Delta 最小的切片（并列时取标签序先出现者），
    以最近邻的组标签作为预测组。

    :param labels: 样本标签列表（与 ``matrix`` 行列对应）
    :param matrix: 两两 Delta 距离矩阵
    :param group_of: ``{样本标签: 组名}``
    :return: ``{"predictions": [{sample, true_group, nn_sample, nn_group, hit}],
                "accuracy": 总体准确率,
                "baseline": 随机基线（最大组样本占比）,
                "per_group": {组名: (命中数, 总数)},
                "n_correct": 命中总数}``
    """
    n = len(labels)
    predictions: List[Dict[str, object]] = []
    per_group_hits: Dict[str, int] = {}
    per_group_total: Dict[str, int] = {}
    n_correct = 0

    for i, la in enumerate(labels):
        best_j = -1
        best_d = math.inf
        row = matrix[i]
        for j in range(n):
            if j == i:
                continue
            d = row[j]
            if d < best_d:
                best_d = d
                best_j = j
        nb = labels[best_j]
        hit = group_of[nb] == group_of[la]
        predictions.append({
            "sample": la,
            "true_group": group_of[la],
            "nn_sample": nb,
            "nn_group": group_of[nb],
            "hit": hit,
        })
        per_group_total[group_of[la]] = per_group_total.get(group_of[la], 0) + 1
        if hit:
            n_correct += 1
            per_group_hits[group_of[la]] = per_group_hits.get(group_of[la], 0) + 1

    group_sizes: Dict[str, int] = {}
    for la in labels:
        group_sizes[group_of[la]] = group_sizes.get(group_of[la], 0) + 1
    baseline = max(group_sizes.values()) / n if n else 0.0

    return {
        "predictions": predictions,
        "accuracy": n_correct / n if n else 0.0,
        "baseline": baseline,
        "per_group": {
            g: (per_group_hits.get(g, 0), per_group_total[g])
            for g in sorted(per_group_total)
        },
        "n_correct": n_correct,
    }


# =============================================================================
# 信号竞争检验
# =============================================================================


def sign_test_pvalue(wins_a: int, wins_b: int) -> float:
    """双侧符号检验（二项检验，H0: p = 0.5），纯 Python 实现。

    :param wins_a: 一方获胜次数
    :param wins_b: 另一方获胜次数（平局应由调用方剔除）
    :return: 双侧 p-value
    """
    n = wins_a + wins_b
    if n == 0:
        return 1.0
    k = min(wins_a, wins_b)
    # p = 2 * P(X <= k), X ~ Bin(n, 0.5)；对 p=0.5 的对称分布即双侧检验
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2.0 * tail)


def _mean_delta(
    matrix: List[List[float]],
    idx_of: Dict[str, int],
    labels_a: List[str],
    labels_b: List[str],
) -> float:
    """两组样本间所有两两 Delta 的均值。"""
    total = 0.0
    count = 0
    for la in labels_a:
        ia = idx_of[la]
        for lb in labels_b:
            total += matrix[ia][idx_of[lb]]
            count += 1
    return total / count if count else 0.0


def signal_competition(
    labels: List[str], matrix: List[List[float]], group_of: Dict[str, str]
) -> Dict[str, object]:
    """信号竞争检验：原文信号 vs 译者信号。

    配对规则：``__chunkNNN`` 后缀去掉后词根相同的篇目，若在两个组中
    都出现，视为同一原作的两个译本。只在单一组中出现的篇目为孤儿篇目，
    跳过并记录在案。

    :param labels: 样本标签列表（与 ``matrix`` 行列对应）
    :param matrix: 两两 Delta 距离矩阵
    :param group_of: ``{样本标签: 组名}``
    :return: ``{"pairs": [每对篇目明细 dict],
                "wins_original": 原文信号获胜次数,
                "wins_translator": 译者信号获胜次数,
                "ties": 平局次数,
                "orphans": 孤儿篇目词根列表,
                "p_value": 符号检验 p-value}``
    """
    idx_of = {label: i for i, label in enumerate(labels)}

    # stem -> {group: [sample labels]}
    works: Dict[str, Dict[str, List[str]]] = {}
    # group -> [全部样本 labels]（按标签序，保证确定性）
    group_members: Dict[str, List[str]] = {}
    for la in labels:
        g = group_of[la]
        works.setdefault(work_stem(la), {}).setdefault(g, []).append(la)
        group_members.setdefault(g, []).append(la)

    groups = sorted(group_members)
    orphans = sorted(s for s, gm in works.items() if len(gm) < 2)

    pairs: List[Dict[str, object]] = []
    wins_original = 0
    wins_translator = 0
    ties = 0

    for ga, gb in combinations(groups, 2):
        common = sorted(
            s for s, gm in works.items() if ga in gm and gb in gm
        )
        for stem in common:
            a_chunks = works[stem][ga]
            b_chunks = works[stem][gb]

            # a) 同篇跨译者距离
            cross_dist = _mean_delta(matrix, idx_of, a_chunks, b_chunks)

            # b) 同译者跨篇距离：本篇目切片 vs 同组其他篇目切片
            others_a = [l for l in group_members[ga]
                        if work_stem(l) != stem]
            others_b = [l for l in group_members[gb]
                        if work_stem(l) != stem]
            within_a = (
                _mean_delta(matrix, idx_of, a_chunks, others_a)
                if others_a else math.nan
            )
            within_b = (
                _mean_delta(matrix, idx_of, b_chunks, others_b)
                if others_b else math.nan
            )
            if math.isnan(within_a) and math.isnan(within_b):
                continue  # 两组都只有这一篇，无法比较跨篇距离
            if math.isnan(within_a):
                same_dist = within_b
            elif math.isnan(within_b):
                same_dist = within_a
            else:
                same_dist = (within_a + within_b) / 2.0

            if cross_dist < same_dist:
                winner = "original"
                wins_original += 1
            elif cross_dist > same_dist:
                winner = "translator"
                wins_translator += 1
            else:
                winner = "tie"
                ties += 1

            pairs.append({
                "work": stem,
                "group_a": ga,
                "group_b": gb,
                "cross_translator_dist": cross_dist,
                "same_translator_dist": same_dist,
                "winner": winner,
            })

    return {
        "pairs": pairs,
        "wins_original": wins_original,
        "wins_translator": wins_translator,
        "ties": ties,
        "orphans": orphans,
        "p_value": sign_test_pvalue(wins_original, wins_translator),
    }
