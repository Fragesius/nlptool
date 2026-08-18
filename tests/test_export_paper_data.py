"""Tests for experiments/export_paper_data.py (v2.3.1 data exports).

Compatible with ``python run_tests.py`` (plain functions, no pytest).

Covers: the merged-fit MFW wordlist, the chunk-level Delta matrix export
(byte format identical to run_delta.py output), the per-dimension
fingerprint score table (weighted total == sum of weight x score), and
the tokenizer control run ([A-Za-z']+, CSVs only).
"""

from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.stylometry import (  # noqa: E402
    build_freq_table,
    delta_matrix,
    tokenize,
    zscore,
)
from core.linguistic_fingerprint import (  # noqa: E402
    FEATURE_WEIGHTS,
    FeatureVector,
    dimension_scores,
    weighted_cosine_similarity,
)
from experiments.export_paper_data import (  # noqa: E402
    _slice_groups,
    control_tokenize,
    export_delta_matrices,
    export_feature_scores,
    export_mfw,
    run_tokenizer_control,
)
from tests import _SAMPLE_DIR, has_matplotlib  # noqa: E402


def _make_corpus(root: Path) -> Path:
    """Two translator groups with matching work stems (sample corpus)."""
    inp = root / "corpus"
    mapping = {
        "translator_A": {"work1": "text_the_a.txt",
                         "work2": "text_the_b.txt"},
        "translator_B": {"work1": "text_of_a.txt",
                         "work2": "text_of_b.txt"},
    }
    for group, works in mapping.items():
        gdir = inp / group
        gdir.mkdir(parents=True)
        for stem, fname in works.items():
            text = next(_SAMPLE_DIR.rglob(fname)).read_text(encoding="utf-8")
            (gdir / f"{stem}.txt").write_text(text, encoding="utf-8")
    return inp


# ── 核心重构不变性 ──────────────────────────────────────────────────────


def test_dimension_scores_match_weighted_total():
    """dimension_scores 的加权和与 weighted_cosine_similarity 逐位一致。"""
    fv_a = FeatureVector(word_length_dist=[1.0, 0.0],
                         function_word_freq=[1.0, 0.0])
    fv_b = FeatureVector(word_length_dist=[1.0, 0.0],
                         function_word_freq=[0.0, 1.0])
    scores = dimension_scores(fv_a, fv_b)
    assert list(scores) == ["word_length_dist", "function_word_freq",
                            "char_ngrams", "word_bigrams",
                            "sentence_stats", "punct_dist",
                            "ttr", "hapax_ratio"]
    total = 0.0
    for key in FEATURE_WEIGHTS:  # 与 weighted_cosine_similarity 同序 +=
        total += FEATURE_WEIGHTS[key] * scores[key]
    assert total == weighted_cosine_similarity(fv_a, fv_b)
    # 旧测试的手算值不变（0.525），确认重构无行为变化
    assert abs(weighted_cosine_similarity(fv_a, fv_b) - 0.525) < 1e-12


def test_build_freq_table_default_unchanged():
    """tokenize_fn 缺省与旧调用逐字节一致。"""
    texts = {"a": "the cat, don't stop. " * 50, "b": "of dogs and cats. " * 50}
    assert build_freq_table(texts) == build_freq_table(texts, tokenize_fn=None)


# ── 分词器对照 ──────────────────────────────────────────────────────────


def test_control_tokenizer_keeps_contractions():
    """[A-Za-z']+ 保留缩略；默认 [A-Za-z]+ 拆开。"""
    text = "Don't stop, it's John's dogs' life."
    assert control_tokenize(text) == ["don't", "stop", "it's",
                                      "john's", "dogs'", "life"]
    assert tokenize(text) == ["don", "t", "stop", "it", "s",
                              "john", "s", "dogs", "life"]


def test_control_changes_freq_table():
    """含缩略词的语料上，对照分词器得到的频率表与默认不同。"""
    texts = {"a": "I don't know, it's fine. " * 100,
             "b": "You can't say it's wrong. " * 100}
    default = build_freq_table(texts, n=20)
    control = build_freq_table(texts, n=20, tokenize_fn=control_tokenize)
    assert default["features"] != control["features"]
    assert "don't" in control["features"]
    assert "don't" not in default["features"]


# ── MFW 词表导出 ────────────────────────────────────────────────────────


def test_export_mfw_merged_fit():
    """mfw 词表 = 合并拟合的 build_freq_table features，一词一行。"""
    if not has_matplotlib():
        print("    (skipped: matplotlib not installed)")
        return

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inp = _make_corpus(root)
        out = root / "data" / "mfw100.txt"
        words = export_mfw(inp, out, top_n=50)

        # 文件内容与直接合并拟合一致
        from experiments.run_experiment import load_groups
        groups = load_groups(inp)
        texts = {la: t for g in groups.values() for la, t in g.items()}
        expected = build_freq_table(texts, n=50)["features"]
        assert words == expected

        raw = out.read_bytes()
        text = raw.decode("utf-8")
        assert text.endswith("\n")
        assert text.splitlines() == words
        assert len(words) == 50


# ── Delta 矩阵导出 ──────────────────────────────────────────────────────


def test_export_delta_matrices_format_and_values():
    """delta_matrix_1k/2k.csv：格式与 run_delta 一致，数值与直接重算一致。"""
    if not has_matplotlib():
        print("    (skipped: matplotlib not installed)")
        return

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inp = _make_corpus(root)
        out_dir = root / "data"
        paths = export_delta_matrices(inp, out_dir, scales=(1000, 2000))
        assert [p.name for p in paths] == ["delta_matrix_1k.csv",
                                           "delta_matrix_2k.csv"]

        from experiments.run_experiment import load_groups
        from experiments.slice_corpus import slice_corpus

        for size, path in ((1000, paths[0]), (2000, paths[1])):
            # 直接重算（与被测代码同路径但独立执行）
            sliced = root / f"check_{size}"
            slice_corpus(inp, sliced, size)
            groups = load_groups(sliced)
            texts = {la: t for g in groups.values() for la, t in g.items()}
            dm = delta_matrix(zscore(build_freq_table(texts, n=100)))
            labels, matrix = dm["labels"], dm["matrix"]

            raw = path.read_bytes()
            assert raw.startswith(b"\xef\xbb\xbf"), "缺 UTF-8 BOM"
            with path.open(newline="", encoding="utf-8-sig") as f:
                table = list(csv.reader(f))
            n = len(labels)
            assert len(table) == n + 1
            assert table[0][0] == "" and table[0][1:] == labels
            for i, row in enumerate(table[1:]):
                assert row[0] == labels[i]
                for j in range(n):
                    assert row[j + 1] == f"{matrix[i][j]:.6f}"
            # 对称、对角为 0
            for i in range(n):
                assert table[i + 1][i + 1] == "0.000000"
                for j in range(i + 1, n):
                    assert table[i + 1][j + 1] == table[j + 1][i + 1]


# ── 八维 per-dimension 得分表 ──────────────────────────────────────────


def test_export_feature_scores():
    """feature_scores.csv：每 chunk × 每尺度一行，weighted_total 与
    八维得分按默认权重的加权和一致（格式化误差内）。"""
    if not has_matplotlib():
        print("    (skipped: matplotlib not installed)")
        return

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inp = _make_corpus(root)
        out = root / "data" / "feature_scores.csv"
        export_feature_scores(inp, out, scales=(1000, 2000))

        with out.open(newline="", encoding="utf-8-sig") as f:
            table = list(csv.reader(f))
        dims = list(FEATURE_WEIGHTS)
        assert table[0] == ["scale", "sample", "group"] + dims \
            + ["weighted_total"]
        # 1k: 3 chunk/篇 × 4 篇 = 12；2k: 2 × 4 = 8
        assert len(table) == 1 + 12 + 8
        scales = {r[0] for r in table[1:]}
        assert scales == {"1k", "2k"}
        for r in table[1:]:
            scores = dict(zip(dims, (float(v) for v in r[3:3 + 8])))
            total = float(r[-1])
            expected = sum(FEATURE_WEIGHTS[k] * scores[k] for k in dims)
            assert abs(total - expected) < 2e-6
            assert r[2] in ("translator_A", "translator_B")


# ── 分词器对照跑 ────────────────────────────────────────────────────────


def test_slice_groups_ignores_stray_outputs():
    """_slice_groups 只切一级组目录：语料根目录里遗留的旧输出
    （无直接 .txt 的子目录，如 weight_sensitivity/sliced_*）不会被当作语料。"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        corp = root / "corpus"
        (corp / "g1").mkdir(parents=True)
        (corp / "g2").mkdir(parents=True)
        (corp / "g1" / "w1.txt").write_text("alpha beta. " * 600,
                                            encoding="utf-8")
        (corp / "g2" / "w1.txt").write_text("gamma delta. " * 600,
                                            encoding="utf-8")
        # 遗留输出：只有嵌套切片，无直接 .txt
        stray = corp / "weight_sensitivity" / "sliced_1000" / "g1"
        stray.mkdir(parents=True)
        (stray / "w1__chunk001.txt").write_text("stale chunk. " * 900,
                                                encoding="utf-8")

        out = root / "sliced"
        n = _slice_groups(corp, out, 500)

        assert n == 4  # 每组 2 块（1200 词 → 500×2 + 尾 200 丢弃）
        assert (out / "g1").is_dir() and (out / "g2").is_dir()
        assert not (out / "weight_sensitivity").exists()


def test_run_tokenizer_control():
    """对照跑：三尺度齐、只产 CSV、组结构正确。"""
    if not has_matplotlib():
        print("    (skipped: matplotlib not installed)")
        return

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inp = _make_corpus(root)
        out_root = root / "results" / "tokenizer_control"
        written = run_tokenizer_control(inp, out_root,
                                        scales=(1000, 2000, 4000))

        assert len(written) == 3 * 4
        for label in ("1k", "2k", "4k"):
            d = out_root / label
            for name in ("delta_matrix.csv", "nn_predictions.csv",
                         "signal_competition.csv", "fingerprint_pairs.csv"):
                assert (d / name).is_file(), f"{label}/{name} missing"
            # 只产 CSV：无图片、无报告
            assert not list(d.glob("*.png"))
            assert not list(d.glob("*.md"))

        # 标签与组归属正确（每篇 4k 切 1 块 → 2 样本/组）
        with (out_root / "4k" / "delta_matrix.csv").open(
                newline="", encoding="utf-8-sig") as f:
            table = list(csv.reader(f))
        labels = table[0][1:]
        assert len(labels) == 4
        assert all("/" in la for la in labels)

        # 1-NN 基线 = 真实多数类比例（两组各半 → 0.5）
        with (out_root / "4k" / "nn_predictions.csv").open(
                newline="", encoding="utf-8-sig") as f:
            nn_rows = list(csv.reader(f))
        assert nn_rows[0] == ["sample", "true_group", "nn_sample",
                              "nn_group", "hit"]
        assert len(nn_rows) == 1 + 4
