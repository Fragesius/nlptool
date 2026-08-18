"""Tests for experiments/group_metrics.py (v2.0.0 阶段二新指标)。

Compatible with ``python run_tests.py`` (plain functions, no pytest).
"""

from __future__ import annotations

import csv
import math
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experiments.group_metrics import (  # noqa: E402
    nearest_neighbor_loo,
    sign_test_pvalue,
    signal_competition,
    work_stem,
)
from tests import _SAMPLE_DIR, has_matplotlib  # noqa: E402


def test_work_stem_strips_chunk_suffix():
    assert work_stem("translator_A/ah_q__chunk001") == "ah_q"
    assert work_stem("translator_B/ah_q__chunk012") == "ah_q"
    assert work_stem("translator_A/plain_name") == "plain_name"
    assert work_stem("no_group") == "no_group"


def _toy_matrix():
    """两组各 2 样本的玩具距离矩阵：组内近、组间远。"""
    labels = ["A/s1", "A/s2", "B/s3", "B/s4"]
    group_of = {"A/s1": "A", "A/s2": "A", "B/s3": "B", "B/s4": "B"}
    # 组内 0.1，组间 0.9
    matrix = [[0.0] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            if i != j:
                same = group_of[labels[i]] == group_of[labels[j]]
                matrix[i][j] = 0.1 if same else 0.9
    return labels, matrix, group_of


def test_1nn_loo_perfect_separation():
    """组内距离远小于组间时，1-NN 准确率应为 100%，基线为最大组占比。"""
    labels, matrix, group_of = _toy_matrix()
    res = nearest_neighbor_loo(labels, matrix, group_of)

    assert res["accuracy"] == 1.0
    assert res["n_correct"] == 4
    assert res["baseline"] == 0.5  # 最大组 2/4
    assert res["per_group"] == {"A": (2, 2), "B": (2, 2)}
    preds = res["predictions"]
    assert len(preds) == 4
    for p in preds:
        assert p["hit"] is True
        assert p["nn_group"] == p["true_group"]
        assert p["nn_sample"] != p["sample"]  # 排除自身


def test_1nn_loo_tie_breaks_by_label_order():
    """最近邻并列时取标签序先出现者，保证确定性。"""
    labels = ["A/s1", "B/s2", "A/s3"]
    group_of = {"A/s1": "A", "B/s2": "B", "A/s3": "A"}
    # s1 到 s2、s3 等距 → 最近邻取先出现的 s2
    matrix = [
        [0.0, 0.5, 0.5],
        [0.5, 0.0, 0.4],
        [0.5, 0.4, 0.0],
    ]
    res = nearest_neighbor_loo(labels, matrix, group_of)
    assert res["predictions"][0]["nn_sample"] == "B/s2"
    assert res["predictions"][0]["hit"] is False
    # 3 组大小为 2/1 → 基线 2/3
    assert abs(res["baseline"] - 2 / 3) < 1e-12


def test_sign_test_known_values():
    """符号检验 p 值与手算二项分布一致。"""
    # n=10, k=0: p = 2 * 1/1024 = 0.001953125
    assert abs(sign_test_pvalue(10, 0) - 2 / 1024) < 1e-12
    # n=10, k=1: p = 2 * (1+10)/1024 = 22/1024
    assert abs(sign_test_pvalue(9, 1) - 22 / 1024) < 1e-12
    # 完全平局：p = 1（2 * P(X<=5), n=10 → 2*638/1024 > 1 → 截断为 1）
    assert sign_test_pvalue(5, 5) == 1.0
    # 无有效对：p = 1
    assert sign_test_pvalue(0, 0) == 1.0


def test_signal_competition_pairing_and_verdict():
    """同词根跨组配对正确；a<b 判原文胜；孤儿篇目被记录。"""
    # 篇目 work1: A 组 2 切片 + B 组 2 切片；work2: A 组 1 切片；orphan: 仅 A 组
    labels = [
        "GA/work1__chunk001", "GA/work1__chunk002",
        "GB/work1__chunk001", "GB/work1__chunk002",
        "GA/work2__chunk001",
        "GA/orphan__chunk001",
    ]
    group_of = {l: l.split("/")[0] for l in labels}
    idx = {l: i for i, l in enumerate(labels)}

    def dist(x, y):
        wx, gx = work_stem(x), group_of[x]
        wy, gy = work_stem(y), group_of[y]
        if wx == wy and gx != gy:
            return 0.2  # 同篇跨译者：近
        if gx == gy and wx != wy:
            return 0.8  # 同译者跨篇：远
        return 0.5      # 其余（跨组跨篇）：中

    n = len(labels)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                matrix[i][j] = dist(labels[i], labels[j])

    res = signal_competition(labels, matrix, group_of)

    # work1 跨组配对（a=0.2 < b=0.8 → 原文胜）；work2 只在 GA → 孤儿
    assert res["orphans"] == ["orphan", "work2"]
    assert len(res["pairs"]) == 1
    pair = res["pairs"][0]
    assert pair["work"] == "work1"
    assert pair["group_a"] == "GA" and pair["group_b"] == "GB"
    assert abs(pair["cross_translator_dist"] - 0.2) < 1e-12
    # 同译者跨篇：GA 的 work1 切片 vs work2+orphan 切片（0.8），
    # GB 无其他篇目 → 取单侧 0.8
    assert abs(pair["same_translator_dist"] - 0.8) < 1e-12
    assert pair["winner"] == "original"
    assert res["wins_original"] == 1
    assert res["wins_translator"] == 0


def test_signal_competition_translator_wins():
    """a>b 时判译者信号胜。"""
    labels = [
        "GA/w__chunk001", "GA/w__chunk002", "GA/x__chunk001",
        "GB/w__chunk001", "GB/w__chunk002", "GB/y__chunk001",
    ]
    group_of = {l: l.split("/")[0] for l in labels}

    def dist(x, y):
        wx, gx = work_stem(x), group_of[x]
        wy, gy = work_stem(y), group_of[y]
        if wx == wy and gx != gy:
            return 0.9  # 同篇跨译者：远 → 译者信号胜
        if gx == gy and wx != wy:
            return 0.1
        return 0.5

    n = len(labels)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                matrix[i][j] = dist(labels[i], labels[j])

    res = signal_competition(labels, matrix, group_of)
    assert res["wins_translator"] == 1
    assert res["wins_original"] == 0
    assert res["p_value"] == 1.0  # 单对无法拒绝 H0


def _build_paired_groups(root: Path) -> Path:
    """用 sample_corpus 构造已知 A/B 分组，且两组含同词根篇目。

    translator_A 取 the 组两篇、translator_B 取 of 组两篇（组级虚词偏差
    保证 1-NN 可分离）；文件名词根 ah_q / kong_yiji 在两组中成对出现，
    供信号竞争检验配对。各篇切成 2 个 1000 词切片，共 12 样本。
    """
    from experiments.slice_corpus import chunk_text

    mapping = {
        "translator_A": {"ah_q": "the/text_the_a.txt",
                         "kong_yiji": "the/text_the_b.txt"},
        "translator_B": {"ah_q": "of/text_of_a.txt",
                         "kong_yiji": "of/text_of_b.txt"},
    }
    inp = root / "input"
    for group, works in mapping.items():
        gdir = inp / group
        gdir.mkdir(parents=True)
        for stem, rel in works.items():
            text = (_SAMPLE_DIR / rel).read_text(encoding="utf-8")
            for k, chunk in enumerate(chunk_text(text, 1000), 1):
                (gdir / f"{stem}__chunk{k:03d}.txt").write_text(
                    chunk, encoding="utf-8"
                )
    return inp


def test_run_experiment_writes_new_artifacts():
    """完整管线产出 nn_predictions.csv 与 signal_competition.csv，
    且 report.md 含两个新指标的章节与中文结论。"""
    if not has_matplotlib():
        print("    (skipped: matplotlib not installed)")
        return

    from experiments.run_experiment import run

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inp = _build_paired_groups(root)
        out = root / "out"

        stats = run(inp, out, perm_n=200)

        for name in ("nn_predictions.csv", "signal_competition.csv"):
            assert (out / name).is_file(), f"missing artifact: {name}"

        # nn_predictions.csv：每切片一行，列为 文件名/真实组/最近邻/最近邻组/命中
        with (out / "nn_predictions.csv").open(encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == stats["n_samples"]
        assert set(rows[0]) == {
            "sample", "true_group", "nn_sample", "nn_group", "hit"}
        assert all(r["hit"] in ("0", "1") for r in rows)

        # signal_competition.csv：每对篇目一行（ah_q + kong_yiji = 2 对）
        with (out / "signal_competition.csv").open(encoding="utf-8-sig") as f:
            sc_rows = list(csv.DictReader(f))
        assert {r["work"] for r in sc_rows} == {"ah_q", "kong_yiji"}
        assert all(r["winner"] in ("original", "translator", "tie")
                   for r in sc_rows)

        # 结果字典含新指标键
        for key in ("nn_accuracy", "nn_baseline", "nn_per_group",
                    "sc_wins_original", "sc_wins_translator",
                    "sc_p_value", "nn_conclusion", "sc_conclusion"):
            assert key in stats, f"result dict missing key: {key}"

        # 已知 A/B 分组：1-NN 准确率应高于随机基线
        assert stats["nn_accuracy"] > stats["nn_baseline"], (
            f"1-NN {stats['nn_accuracy']:.4f} 未超过基线 "
            f"{stats['nn_baseline']:.4f}"
        )

        report = (out / "report.md").read_text(encoding="utf-8")
        assert "## 1-NN Leave-One-Out Classification" in report
        assert "## Signal Competition Test" in report
        assert "符号检验" in report
