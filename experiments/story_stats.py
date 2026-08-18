"""Story-level statistics and robustness checks (v2.2.0).

Built on top of the artifacts already computed by
``experiments.run_experiment.run`` — the pairwise fingerprint similarity
dict, the Delta matrix and the group mapping — without touching any of
the existing outputs:

1. ``story_wilcoxon``: story-level Wilcoxon signed-rank test. For each
   story (``work_stem``) present in at least two groups, the mean
   same-translator similarity of the story's chunks minus the mean
   cross-translator similarity gives one paired observation ``diff_s``;
   the diffs are tested two-sided. Reports W, p and the matched-pairs
   rank-biserial correlation r as effect size.

2. ``bootstrap_d_ci``: story-level bootstrap confidence interval for
   Cohen's d. Stories are resampled with replacement (n stories drawn
   n times); each replicate recomputes Cohen's d from all chunks of the
   sampled stories with the same convention as the existing
   implementation (same-translator vs cross-translator pair similarity
   difference over the pooled sample standard deviation). The RNG uses
   its own seed (default 20260818) and never touches the permutation
   test's random stream.

3. ``equal_chunk_robustness``: equal-chunk robustness check. Every
   story x translator cell is downsampled to the cell minimum (first k
   chunks by chunk number, deterministic); the signal competition test
   and Cohen's d are recomputed on the balanced corpus.

All functions are pure-Python and deterministic.
"""

from __future__ import annotations

import math
import random
import re
from typing import Dict, List, Optional, Tuple

from core.linguistic_fingerprint import cohens_d  # noqa: E402
from experiments.group_metrics import (  # noqa: E402
    signal_competition,
    work_stem,
)

__all__ = [
    "story_same_cross_sims",
    "wilcoxon_stats",
    "bootstrap_d_ci",
    "equal_chunk_filter",
    "equal_chunk_robustness",
]

DEFAULT_BOOT_SEED = 20260818

_CHUNK_NUM_RE = re.compile(r"__chunk(\d+)$")


def _pair_sim(sim_pair: Dict[Tuple[str, str], float], a: str, b: str) -> float:
    return sim_pair[(a, b)] if (a, b) in sim_pair else sim_pair[(b, a)]


# =============================================================================
# 任务一：故事级 Wilcoxon
# =============================================================================


def story_same_cross_sims(
    labels: List[str],
    group_of: Dict[str, str],
    sim_pair: Dict[Tuple[str, str], float],
) -> Dict[str, Dict[str, List[float]]]:
    """每个故事的同译者/跨译者指纹相似度列表。

    同译者对：同一故事、同一组内的切片两两配对；
    跨译者对：同一故事、不同组之间的切片两两配对。

    :return: ``{story: {"same": [...], "cross": [...]}}``
    """
    stories: Dict[str, Dict[str, List[str]]] = {}
    for la in labels:
        stories.setdefault(work_stem(la), {}).setdefault(
            group_of[la], []).append(la)

    out: Dict[str, Dict[str, List[float]]] = {}
    for story, gm in stories.items():
        same: List[float] = []
        cross: List[float] = []
        for ls in gm.values():
            for i in range(len(ls)):
                for j in range(i + 1, len(ls)):
                    same.append(_pair_sim(sim_pair, ls[i], ls[j]))
        groups = sorted(gm)
        for ai in range(len(groups)):
            for bi in range(ai + 1, len(groups)):
                for la in gm[groups[ai]]:
                    for lb in gm[groups[bi]]:
                        cross.append(_pair_sim(sim_pair, la, lb))
        out[story] = {"same": same, "cross": cross}
    return out


def wilcoxon_stats(differences: List[float]) -> Dict[str, float]:
    """Wilcoxon 符号秩检验（双侧），返回 W、p 与 rank-biserial r。

    标准定义的平均秩与正态近似（与 scipy ``wilcoxon`` 的近似口径一致，
    可用小样本手算验证）；统计量 W = min(W+, W-)，效应量
    r = (W+ - W-) / T，T = n(n+1)/2（matched-pairs rank-biserial
    correlation）。p 为正态近似（无连续性校正、无平局方差校正）。

    :param differences: 配对观测差值列表（零差值剔除，与既有实现一致）
    :return: ``{"n": 有效对数, "w_plus": W+, "w_minus": W-,
                "W": min(W+,W-), "z": 正态近似 z, "p": 双侧 p,
                "r": rank-biserial 相关系数}``
    """
    diffs = [d for d in differences if d != 0.0]
    n = len(diffs)
    if n < 3:
        return {"n": n, "w_plus": 0.0, "w_minus": 0.0,
                "W": 0.0, "z": 0.0, "p": 1.0, "r": 0.0}

    indexed = [(abs(d), d > 0) for d in diffs]
    indexed.sort(key=lambda x: x[0])

    # 直接在排序后的序列上累加带符号秩（平局取平均秩）
    w_plus = 0.0
    w_minus = 0.0
    j = 0
    while j < n:
        k = j
        while k < n and indexed[k][0] == indexed[j][0]:
            k += 1
        # 位置 j..k-1（0-indexed）对应秩 j+1..k（1-indexed）。
        # core.linguistic_fingerprint.wilcoxon_signed_rank_test 自 v2.3.2
        # 起已修复为同一标准定义（此前平均秩与秩-符号配对有偏差）；
        # 本函数按标准定义实现，可与 scipy / 手算对照。
        avg_rank = (j + k + 1) / 2.0
        for m in range(j, k):
            if indexed[m][1]:
                w_plus += avg_rank
            else:
                w_minus += avg_rank
        j = k
    w_stat = min(w_plus, w_minus)

    expected = n * (n + 1) / 4.0
    std = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0)
    if std < 1e-12:
        return {"n": n, "w_plus": w_plus, "w_minus": w_minus,
                "W": w_stat, "z": 0.0, "p": 1.0, "r": 0.0}

    z = (w_stat - expected) / std
    # 双侧正态近似（与 wilcoxon_signed_rank_test 同口径：用 |z| 防 p > 1）
    p = 2.0 * (1.0 - _normal_cdf(abs(z)))
    p = min(max(p, 0.0), 1.0)
    total = n * (n + 1) / 2.0
    r = (w_plus - w_minus) / total if total > 0 else 0.0
    return {"n": n, "w_plus": w_plus, "w_minus": w_minus,
            "W": w_stat, "z": z, "p": p, "r": r}


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def story_wilcoxon(
    labels: List[str],
    group_of: Dict[str, str],
    sim_pair: Dict[Tuple[str, str], float],
) -> Dict[str, object]:
    """故事级 Wilcoxon：每个故事一个 diff_s，整体做符号秩检验。

    只有同时具备同译者对与跨译者对的故事才计入（每组各 1 片的故事
    没有同译者对，跳过）。

    :return: ``{"diffs": {story: diff_s}, "mean_diff": 均值,
                "stats": wilcoxon_stats 结果}``
    """
    per_story = story_same_cross_sims(labels, group_of, sim_pair)
    diffs: Dict[str, float] = {}
    for story in sorted(per_story):
        same = per_story[story]["same"]
        cross = per_story[story]["cross"]
        if not same or not cross:
            continue
        diffs[story] = (sum(same) / len(same)) - (sum(cross) / len(cross))
    values = [diffs[s] for s in sorted(diffs)]
    mean_diff = sum(values) / len(values) if values else 0.0
    return {
        "diffs": diffs,
        "mean_diff": mean_diff,
        "stats": wilcoxon_stats(values),
    }


# =============================================================================
# 任务二：Cohen's d 的故事级 bootstrap 置信区间
# =============================================================================


def _d_from_sums(
    n_s: float, s_s: float, q_s: float,
    n_c: float, s_c: float, q_c: float,
) -> Optional[float]:
    """由 (计数, 和, 平方和) 重算 Cohen's d（口径与现有实现一致）。

    返回 None 表示该样本无法计算（任一侧配对数 < 2）。
    """
    if n_s < 2 or n_c < 2:
        return None
    m_s = s_s / n_s
    m_c = s_c / n_c
    v_s = max(0.0, (q_s - s_s * s_s / n_s) / (n_s - 1))
    v_c = max(0.0, (q_c - s_c * s_c / n_c) / (n_c - 1))
    return cohens_d(m_s, m_c, math.sqrt(v_s), math.sqrt(v_c),
                    int(n_s), int(n_c))


def _percentile(sorted_xs: List[float], q: float) -> float:
    """线性插值百分位数（q ∈ [0,1]），输入须已排序。"""
    if not sorted_xs:
        return math.nan
    if len(sorted_xs) == 1:
        return sorted_xs[0]
    pos = q * (len(sorted_xs) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sorted_xs) - 1)
    frac = pos - lo
    return sorted_xs[lo] * (1.0 - frac) + sorted_xs[hi] * frac


def bootstrap_d_ci(
    labels: List[str],
    group_of: Dict[str, str],
    sim_pair: Dict[Tuple[str, str], float],
    n_iter: int = 10000,
    seed: int = DEFAULT_BOOT_SEED,
) -> Dict[str, object]:
    """故事级 bootstrap：重抽故事，重算 Cohen's d，报 95% 百分位 CI。

    抽样单位为故事（work_stem）：每次迭代有放回抽 n_stories 个故事，
    被抽中故事的全部切片按抽中次数计入。同译者对 = 同组切片对，
    跨译者对 = 跨组切片对（不限于同故事，与现有 d 的口径一致）。

    RNG 为独立的 ``random.Random(seed)``，不影响置换检验的随机流。

    :return: ``{"n_stories", "n_iter", "n_valid", "d_observed",
                "ci_low", "ci_high"}``
    """
    stories = sorted({work_stem(l) for l in labels})
    n_stories = len(stories)

    # 按 (故事对, 是否同组) 聚合配对的 (count, sum, sumsq)，
    # 使每次 bootstrap 迭代只需 O(故事对数) 而不是 O(切片对数)。
    # 键: (story_a, story_b, is_same_group)，story_a <= story_b
    agg: Dict[Tuple[str, str, bool], List[float]] = {}
    for (la, lb), sim in sim_pair.items():
        sa, sb = work_stem(la), work_stem(lb)
        key = (min(sa, sb), max(sa, sb), group_of[la] == group_of[lb])
        a = agg.setdefault(key, [0.0, 0.0, 0.0])
        a[0] += 1.0
        a[1] += sim
        a[2] += sim * sim

    def _accumulate(weights: Dict[str, int]) -> Optional[float]:
        n_s = s_s = q_s = n_c = s_c = q_c = 0.0
        for (sa, sb, is_same), (cnt, ssum, sqq) in agg.items():
            # 故事 s 被抽中 w 次时其切片出现 w 份拷贝；
            # 两个不同切片的配对拷贝数为 w_a * w_b（s_a == s_b 时同为 w^2）
            w = weights.get(sa, 0) * weights.get(sb, 0)
            if w == 0:
                continue
            if is_same:
                n_s += w * cnt
                s_s += w * ssum
                q_s += w * sqq
            else:
                n_c += w * cnt
                s_c += w * ssum
                q_c += w * sqq
        return _d_from_sums(n_s, s_s, q_s, n_c, s_c, q_c)

    full_weights = {s: 1 for s in stories}
    d_observed = _accumulate(full_weights)

    rng = random.Random(seed)
    ds: List[float] = []
    for _ in range(n_iter):
        draw = rng.choices(stories, k=n_stories)
        weights: Dict[str, int] = {}
        for s in draw:
            weights[s] = weights.get(s, 0) + 1
        d = _accumulate(weights)
        if d is not None and math.isfinite(d):
            ds.append(d)
    ds.sort()

    return {
        "n_stories": n_stories,
        "n_iter": n_iter,
        "n_valid": len(ds),
        "d_observed": d_observed if d_observed is not None else math.nan,
        "ci_low": _percentile(ds, 0.025),
        "ci_high": _percentile(ds, 0.975),
    }


# =============================================================================
# 任务三：equal-chunk 稳健性检验
# =============================================================================


def _chunk_sort_key(label: str) -> Tuple[int, str]:
    """按 chunk 编号排序（无 __chunkNNN 后缀者编号视为 0），标签序兜底。"""
    stem = label.split("/", 1)[-1]
    m = _CHUNK_NUM_RE.search(stem)
    return (int(m.group(1)) if m else 0, label)


def equal_chunk_filter(
    labels: List[str],
    group_of: Dict[str, str],
) -> Tuple[List[str], int]:
    """把每个 故事×译者 单元向下抽样到该故事各组切片数的最小值。

    只保留出现在至少两个组中的故事；每个故事每组取按 chunk 编号
    排序后的前 k 片（k = 该故事各组切片数的最小值），确定性选择。

    :return: ``(保留的标签列表（排序后）, 参与的故事数)``
    """
    stories: Dict[str, Dict[str, List[str]]] = {}
    for la in labels:
        stories.setdefault(work_stem(la), {}).setdefault(
            group_of[la], []).append(la)

    kept: List[str] = []
    n_stories = 0
    for story in sorted(stories):
        gm = stories[story]
        if len(gm) < 2:
            continue
        k = min(len(ls) for ls in gm.values())
        n_stories += 1
        for g in sorted(gm):
            kept.extend(sorted(gm[g], key=_chunk_sort_key)[:k])
    return sorted(kept), n_stories


def equal_chunk_robustness(
    labels: List[str],
    matrix: List[List[float]],
    group_of: Dict[str, str],
    sim_pair: Dict[Tuple[str, str], float],
) -> Dict[str, object]:
    """在等量抽样后的均衡语料上重跑信号竞争与 Cohen's d。

    :return: ``{"kept_labels", "n_stories", "wins_original",
                "wins_translator", "ties", "p_value", "cohens_d",
                "n_same_pairs", "n_cross_pairs"}``
    """
    kept, n_stories = equal_chunk_filter(labels, group_of)
    kept_set = set(kept)
    idx_of = {label: i for i, label in enumerate(labels)}
    sub_matrix = [[matrix[idx_of[a]][idx_of[b]] for b in kept] for a in kept]

    sc = signal_competition(kept, sub_matrix, group_of)

    same_sims: List[float] = []
    cross_sims: List[float] = []
    for (la, lb), sim in sim_pair.items():
        if la not in kept_set or lb not in kept_set:
            continue
        if group_of[la] == group_of[lb]:
            same_sims.append(sim)
        else:
            cross_sims.append(sim)

    d_val = math.nan
    if len(same_sims) >= 2 and len(cross_sims) >= 2:
        mean_s = sum(same_sims) / len(same_sims)
        mean_c = sum(cross_sims) / len(cross_sims)
        var_s = sum((v - mean_s) ** 2 for v in same_sims) / (len(same_sims) - 1)
        var_c = sum((v - mean_c) ** 2 for v in cross_sims) / (len(cross_sims) - 1)
        d_val = cohens_d(mean_s, mean_c, math.sqrt(var_s), math.sqrt(var_c),
                         len(same_sims), len(cross_sims))

    return {
        "kept_labels": kept,
        "n_stories": n_stories,
        "wins_original": sc["wins_original"],
        "wins_translator": sc["wins_translator"],
        "ties": sc["ties"],
        "p_value": sc["p_value"],
        "cohens_d": d_val,
        "n_same_pairs": len(same_sims),
        "n_cross_pairs": len(cross_sims),
    }
