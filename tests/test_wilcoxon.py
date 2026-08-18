"""Tests for the v2.3.2 Wilcoxon signed-rank fix (core.linguistic_fingerprint).

core 的 wilcoxon_signed_rank_test 此前有两处偏差：平均秩公式多加了 0.5，
且 zip(ranks, indexed) 把按原始下标存储的秩与按排序顺序的符号错配。
v2.3.2 修复为标准定义（与 story_stats.wilcoxon_stats 同口径）。本文件用手算
小样本、story_stats 一致性对拍和可选的 scipy 对拍锁定修复结果。

Compatible with ``python run_tests.py`` (plain functions, no pytest).
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.linguistic_fingerprint import (  # noqa: E402
    _wilcoxon_rank_sums,
    wilcoxon_signed_rank_test,
)
from experiments.story_stats import wilcoxon_stats  # noqa: E402
from tests import has_scipy  # noqa: E402


def test_wilcoxon_handcalc_rank_sums():
    """[1,2,3,4,-1]：|d| 排序后 1(+)/1(-) 平局秩 1.5，其余秩 3/4/5。

    W+ = 1.5+3+4+5 = 13.5，W- = 1.5，W = min = 1.5。
    """
    w_plus, w_minus = _wilcoxon_rank_sums([1.0, 2.0, 3.0, 4.0, -1.0])
    assert w_plus == 13.5
    assert w_minus == 1.5
    assert min(w_plus, w_minus) == 1.5


def test_wilcoxon_handcalc_p_value():
    """同一组差值的双侧 p 与 story_stats.wilcoxon_stats 逐位一致。"""
    diffs = [1.0, 2.0, 3.0, 4.0, -1.0]
    p_core = wilcoxon_signed_rank_test(diffs)
    p_ref = wilcoxon_stats(diffs)["p"]
    assert math.isclose(p_core, p_ref, rel_tol=0.0, abs_tol=1e-12)


def test_wilcoxon_ties_and_signs():
    """平局与符号交错的秩和：构造 [-1, 1, -2, 2, 3] 手算对照。

    |d| = 1,1,2,2,3 → 秩 1.5,1.5 / 3.5,3.5 / 5。
    W+ = 1.5(+1) + 3.5(+2) + 5(+3) = 10.0，W- = 1.5 + 3.5 = 5.0。
    """
    w_plus, w_minus = _wilcoxon_rank_sums([-1.0, 1.0, -2.0, 2.0, 3.0])
    assert w_plus == 10.0
    assert w_minus == 5.0


def test_wilcoxon_edge_cases():
    """零差值剔除与小样本保底行为不变。"""
    assert wilcoxon_signed_rank_test([0.0, 0.0, 0.0]) == 1.0
    assert wilcoxon_signed_rank_test([1.0, -1.0]) == 1.0  # n<3
    assert wilcoxon_signed_rank_test([]) == 1.0


def test_wilcoxon_matches_story_stats_random():
    """200 组随机差值：core 与 story_stats（已对 scipy 验证的实现）对拍。"""
    rng = random.Random(20260818)
    for _ in range(200):
        n = rng.randint(3, 40)
        diffs = [rng.uniform(-5.0, 5.0) or 1e-9 for _ in range(n)]
        p_core = wilcoxon_signed_rank_test(diffs)
        p_ref = wilcoxon_stats(diffs)["p"]
        assert math.isclose(p_core, p_ref, rel_tol=0.0, abs_tol=1e-12), (
            f"n={n}: core={p_core}, story_stats={p_ref}")


def test_wilcoxon_matches_scipy_random():
    """200 组随机差值与 scipy.stats.wilcoxon（正态近似口径）对拍。

    随机连续差值无精确平局/零值，scipy 的平局校正项为零，
    与项目实现（无连续性校正、无平局方差校正）同口径。
    无 scipy 时跳过。
    """
    if not has_scipy():
        print("    (skipped: scipy not installed)")
        return
    from scipy.stats import wilcoxon as sp_wilcoxon

    rng = random.Random(20260818)
    for _ in range(200):
        n = rng.randint(3, 40)
        diffs = [rng.uniform(-5.0, 5.0) or 1e-9 for _ in range(n)]
        p_core = wilcoxon_signed_rank_test(diffs)
        p_sp = sp_wilcoxon(diffs, method="approx").pvalue
        assert math.isclose(p_core, p_sp, rel_tol=0.0, abs_tol=1e-9), (
            f"n={n}: core={p_core}, scipy={p_sp}")
