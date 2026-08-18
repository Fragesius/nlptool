"""Tests for experiments/story_stats.py (v2.2.0 story-level statistics).

Compatible with ``python run_tests.py`` (plain functions, no pytest).

数值正确性用构造数据验证：Wilcoxon 的 W / p / r 与手算小样本对照；
bootstrap 的 d_observed 与直接重算的 Cohen's d 对照，并验证独立
种子的可复现性。流水线测试沿用 tests.test_experiment 的 sample_corpus
分组构造，检查三个新 CSV 齐全、字段完整、report.md 末尾追加新章节。
"""

from __future__ import annotations

import csv
import math
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experiments.story_stats import (  # noqa: E402
    bootstrap_d_ci,
    equal_chunk_filter,
    equal_chunk_robustness,
    story_same_cross_sims,
    story_wilcoxon,
    wilcoxon_stats,
)
from core.linguistic_fingerprint import cohens_d  # noqa: E402
from tests import has_matplotlib  # noqa: E402


# ── 构造数据工具 ──────────────────────────────────────────────────────


def _make_dataset(stories, groups=("A", "B"), chunks_per_cell=2,
                  same_sim=0.8, cross_sim=0.2, jitter=0.05):
    """构造 labels / group_of / sim_pair。

    同组对相似度围绕 ``same_sim``、跨组对围绕 ``cross_sim`` 小幅波动，
    保证两侧方差非零且 same > cross。
    """
    labels = []
    group_of = {}
    for s in stories:
        for g in groups:
            for k in range(1, chunks_per_cell + 1):
                la = f"{g}/{s}__chunk{k:03d}"
                labels.append(la)
                group_of[la] = g
    labels.sort()
    sim_pair = {}
    k = 0
    for i, la in enumerate(labels):
        for lb in labels[i + 1:]:
            base = same_sim if group_of[la] == group_of[lb] else cross_sim
            # 确定性抖动，保证方差非零
            sim = base + jitter * ((k % 5) - 2) / 2.0
            sim_pair[(la, lb)] = sim
            k += 1
    return labels, group_of, sim_pair


def _reference_d(labels, group_of, sim_pair):
    """独立重算 Cohen's d（同译者对均值差 / 合并样本标准差）。"""
    same = [s for (a, b), s in sim_pair.items() if group_of[a] == group_of[b]]
    cross = [s for (a, b), s in sim_pair.items() if group_of[a] != group_of[b]]
    m_s = sum(same) / len(same)
    m_c = sum(cross) / len(cross)
    v_s = sum((v - m_s) ** 2 for v in same) / (len(same) - 1)
    v_c = sum((v - m_c) ** 2 for v in cross) / (len(cross) - 1)
    return cohens_d(m_s, m_c, math.sqrt(v_s), math.sqrt(v_c),
                    len(same), len(cross))


# ── 任务一：Wilcoxon 数值正确性 ──────────────────────────────────────


def test_wilcoxon_stats_handcalc():
    """diffs = [1,2,3,4,-1]：W、r 手算对照，p 与 erfc 公式对照。"""
    res = wilcoxon_stats([1.0, 2.0, 3.0, 4.0, -1.0])
    assert res["n"] == 5
    # |d| 排序: 1,1,2,3,4 → 秩 1.5,1.5,3,4,5；负号只有最后一个 1
    assert res["w_plus"] == 13.5
    assert res["w_minus"] == 1.5
    assert res["W"] == 1.5
    assert abs(res["r"] - 0.8) < 1e-12  # (13.5-1.5)/15
    # z = (1.5 - 7.5) / sqrt(5*6*11/24) = -6/sqrt(13.75)
    z_abs = 6.0 / math.sqrt(13.75)
    p_expected = math.erfc(z_abs / math.sqrt(2.0))
    assert abs(res["p"] - p_expected) < 1e-9


def test_wilcoxon_stats_ties_and_zeros():
    """零差值剔除；n<3 时 p=1；平局用平均秩。"""
    assert wilcoxon_stats([0.0, 0.0])["n"] == 0
    assert wilcoxon_stats([1.0, -1.0])["p"] == 1.0
    res = wilcoxon_stats([1.0, 1.0, -1.0, 2.0])
    assert res["n"] == 4
    # |d|: 1,1,1,2 → 秩 2,2,2,4；w+ = 2+2+4=8, w- = 2
    assert res["w_plus"] == 8.0 and res["w_minus"] == 2.0
    assert abs(res["r"] - 0.6) < 1e-12  # (8-2)/10


def test_story_wilcoxon_on_constructed_data():
    """same > cross 的构造语料上 diff_s 全为正，r = 1。"""
    labels, group_of, sim_pair = _make_dataset(["s1", "s2", "s3", "s4"])
    res = story_wilcoxon(labels, group_of, sim_pair)
    assert len(res["diffs"]) == 4
    for d in res["diffs"].values():
        assert d > 0
    assert res["stats"]["n"] == 4
    assert res["stats"]["r"] == 1.0
    # 全正、n=4：W=0, z = -5/sqrt(7.5), 双侧 p ≈ 0.0679
    assert 0.06 < res["stats"]["p"] < 0.08
    # diff_s 与 story_same_cross_sims 的直接均值差一致
    per_story = story_same_cross_sims(labels, group_of, sim_pair)
    for story, d in res["diffs"].items():
        same = per_story[story]["same"]
        cross = per_story[story]["cross"]
        assert abs(d - (sum(same) / len(same) - sum(cross) / len(cross))) < 1e-12


# ── 任务二：bootstrap 数值正确性 ─────────────────────────────────────


def test_bootstrap_d_observed_matches_direct():
    """d_observed 与独立重算的 Cohen's d 完全一致。"""
    labels, group_of, sim_pair = _make_dataset(["s1", "s2", "s3"])
    res = bootstrap_d_ci(labels, group_of, sim_pair, n_iter=50, seed=1)
    assert abs(res["d_observed"] - _reference_d(labels, group_of, sim_pair)) < 1e-9
    assert res["n_stories"] == 3


def test_bootstrap_ci_reproducible_and_direction():
    """同种子完全复现；same > cross 的语料上 95% CI 整体为正。"""
    labels, group_of, sim_pair = _make_dataset(
        [f"s{i}" for i in range(1, 7)], same_sim=0.85, cross_sim=0.15)
    r1 = bootstrap_d_ci(labels, group_of, sim_pair, n_iter=300, seed=20260818)
    r2 = bootstrap_d_ci(labels, group_of, sim_pair, n_iter=300, seed=20260818)
    assert r1["ci_low"] == r2["ci_low"] and r1["ci_high"] == r2["ci_high"]
    assert r1["n_valid"] == 300
    assert r1["ci_low"] > 0.0, f"CI 下界应为正: {r1['ci_low']}"
    assert r1["ci_low"] < r1["ci_high"]


def test_bootstrap_rng_independent_stream():
    """bootstrap 使用独立 RNG，不消耗全局/置换检验随机流。"""
    import random as stdlib_random
    from core.linguistic_fingerprint import permutation_test

    labels, group_of, sim_pair = _make_dataset(["s1", "s2", "s3"])
    state_before = stdlib_random.getstate()
    bootstrap_d_ci(labels, group_of, sim_pair, n_iter=100, seed=20260818)
    assert stdlib_random.getstate() == state_before, "全局随机流被扰动"
    # 与置换检验（seed=42）互不影响：各自重复调用结果一致
    same = [0.9, 0.8, 0.85]
    cross = [0.2, 0.3, 0.25]
    p1 = permutation_test(same, cross, n_iter=100)
    bootstrap_d_ci(labels, group_of, sim_pair, n_iter=100, seed=20260818)
    p2 = permutation_test(same, cross, n_iter=100)
    assert p1 == p2


# ── 任务三：equal-chunk 稳健性 ────────────────────────────────────────


def test_equal_chunk_filter_downsamples_to_min():
    """3 片 vs 2 片的故事两边各取前 2 片；孤儿故事被剔除。"""
    labels = [
        "A/s1__chunk001", "A/s1__chunk002", "A/s1__chunk003",
        "B/s1__chunk001", "B/s1__chunk002",
        "A/s2__chunk001",  # 孤儿故事：只在 A 组
    ]
    group_of = {l: l.split("/", 1)[0] for l in labels}
    kept, n_stories = equal_chunk_filter(labels, group_of)
    assert n_stories == 1
    assert kept == [
        "A/s1__chunk001", "A/s1__chunk002",
        "B/s1__chunk001", "B/s1__chunk002",
    ]


def test_equal_chunk_robustness_on_constructed_data():
    """均衡语料上信号竞争与 d 均能算出，字段完整。"""
    labels, group_of, sim_pair = _make_dataset(
        ["s1", "s2", "s3"], chunks_per_cell=2)
    # 造一个 Delta 距离矩阵：同组 0.5，跨组 1.5（译者信号胜）
    idx = {l: i for i, l in enumerate(labels)}
    matrix = [[0.0 if a == b else (0.5 if group_of[a] == group_of[b] else 1.5)
               for b in labels] for a in labels]
    res = equal_chunk_robustness(labels, matrix, group_of, sim_pair)
    assert res["n_stories"] == 3
    assert len(res["kept_labels"]) == 12  # 3 故事 × 2 组 × 2 片
    assert res["wins_translator"] == 3
    assert res["wins_original"] == 0
    assert res["cohens_d"] > 0
    assert res["n_same_pairs"] > 0 and res["n_cross_pairs"] > 0
    assert 0.0 <= res["p_value"] <= 1.0


# ── 流水线集成：sample_corpus 跑通、产物齐全 ─────────────────────────


def test_run_experiment_story_artifacts():
    """完整流水线产出三个新 CSV 且 report.md 末尾追加新章节。"""
    if not has_matplotlib():
        print("    (skipped: matplotlib not installed)")
        return

    from experiments.run_experiment import run
    from tests.test_experiment import _build_groups

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inp = _build_groups(
            root,
            {
                "translator_A": ["text_the_a.txt", "text_the_b.txt"],
                "translator_B": ["text_of_a.txt", "text_of_b.txt"],
            },
            chunk_size=1000,
        )
        out = root / "out"
        stats = run(inp, out, perm_n=200, boot_n=200, scale="1k")

        # 三个新 CSV 齐全且字段完整
        expected_headers = {
            "story_level_tests.csv":
                ["scale", "n_stories", "mean_diff",
                 "wilcoxon_w", "p_value", "rank_biserial_r"],
            "d_bootstrap_ci.csv":
                ["scale", "n_stories", "n_iter",
                 "d_observed", "ci_low", "ci_high"],
            "equal_chunk_robustness.csv":
                ["scale", "n_stories", "kept_chunks",
                 "wins_original", "wins_translator", "ties",
                 "sign_test_p", "cohens_d"],
        }
        for name, header in expected_headers.items():
            path = out / name
            assert path.is_file(), f"missing artifact: {name}"
            with path.open("r", newline="", encoding="utf-8-sig") as f:
                rows = list(csv.reader(f))
            assert rows[0] == header, f"{name} 表头不符: {rows[0]}"
            assert len(rows) == 2 and len(rows[1]) == len(header), (
                f"{name} 应有一行与表头等长的数据")
            assert rows[1][0] == "1k", f"{name} scale 列应为 1k"

        # 既有产物仍然存在
        for name in ("delta_matrix.csv", "dendrogram.png",
                     "fingerprint_pairs.csv", "nn_predictions.csv",
                     "signal_competition.csv", "report.md"):
            assert (out / name).is_file(), f"missing artifact: {name}"

        # report.md 既有章节仍在，新章节追加在结论之后
        report = (out / "report.md").read_text(encoding="utf-8")
        assert "## 结论" in report
        pos_concl = report.index("## 结论")
        for heading in ("## Story-Level Wilcoxon Test",
                        "## Story-Level Bootstrap CI for Cohen's d",
                        "## Equal-Chunk Robustness"):
            assert heading in report, f"缺少章节: {heading}"
            assert report.index(heading) > pos_concl, (
                f"{heading} 应追加在结论之后")

        # 结果字典的新字段
        for key in ("story_wilcoxon_p", "story_wilcoxon_r",
                    "d_bootstrap_ci_low", "d_bootstrap_ci_high",
                    "eq_wins_original", "eq_wins_translator",
                    "eq_p_value", "eq_cohens_d"):
            assert key in stats, f"result dict missing key: {key}"

        # sample_corpus 的词根不跨组重复，故事级配对为 0 属预期
        assert stats["eq_n_stories"] == 0
        assert stats["story_wilcoxon_n"] == 0
