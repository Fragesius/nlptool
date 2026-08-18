"""Tests for experiments/weight_sensitivity.py (v2.3.0 weight sensitivity).

Compatible with ``python run_tests.py`` (plain functions, no pytest).

Covers: weight variant generation (default/uniform/lodo/single/random,
independent RNG streams), the weights override on
``weighted_cosine_similarity`` (default path byte-identical), the
decoupling of the headline Delta pipeline from the weight configuration
(source scan + functional check), and the end-to-end CSV/report outputs
on the synthetic sample corpus.
"""

from __future__ import annotations

import csv
import random
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.linguistic_fingerprint import (  # noqa: E402
    FEATURE_WEIGHTS,
    FeatureVector,
    weighted_cosine_similarity,
)
from experiments.weight_sensitivity import (  # noqa: E402
    DIMENSIONS,
    RANDOM_BASE_SEED,
    RANDOM_VARIANTS,
    variants_for_scheme,
    run_sensitivity,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SAMPLE_DIR = _REPO_ROOT / "experiments" / "sample_corpus"


def _has_matplotlib() -> bool:
    try:
        import matplotlib  # noqa: F401
        return True
    except ImportError:
        return False


# ── 变体生成 ──────────────────────────────────────────────────────────


def test_variants_default_matches_feature_weights():
    """default: exactly the existing FEATURE_WEIGHTS, one variant."""
    variants = variants_for_scheme("default")
    assert len(variants) == 1
    name, w = variants[0]
    assert name == "default"
    assert w == dict(FEATURE_WEIGHTS)
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_variants_uniform():
    """uniform: all eight dimensions at 1/8."""
    variants = variants_for_scheme("uniform")
    assert len(variants) == 1
    name, w = variants[0]
    assert name == "uniform"
    assert len(w) == 8
    for k in DIMENSIONS:
        assert abs(w[k] - 1.0 / 8) < 1e-12


def test_variants_lodo():
    """lodo: 8 variants; one dimension zeroed, rest keep proportions."""
    variants = variants_for_scheme("lodo")
    assert len(variants) == 8
    assert [n for n, _ in variants] == [f"lodo_{d}" for d in DIMENSIONS]
    for name, w in variants:
        dropped = name[len("lodo_"):]
        assert w[dropped] == 0.0
        assert abs(sum(w.values()) - 1.0) < 1e-9
        # Remaining dimensions keep the original proportions.
        kept = [k for k in DIMENSIONS if k != dropped]
        ratios = [w[k] / FEATURE_WEIGHTS[k] for k in kept]
        assert max(ratios) - min(ratios) < 1e-9


def test_variants_single():
    """single: 8 one-hot variants."""
    variants = variants_for_scheme("single")
    assert len(variants) == 8
    assert [n for n, _ in variants] == [f"single_{d}" for d in DIMENSIONS]
    for name, w in variants:
        kept = name[len("single_"):]
        assert w[kept] == 1.0
        assert all(w[k] == 0.0 for k in DIMENSIONS if k != kept)


def test_variants_random_reproducible_and_independent():
    """random: 20 seeds from 20260818, reproducible, own RNG stream."""
    v1 = variants_for_scheme("random")
    assert len(v1) == RANDOM_VARIANTS
    assert v1[0][0] == f"random_{RANDOM_BASE_SEED}"
    assert v1[-1][0] == f"random_{RANDOM_BASE_SEED + RANDOM_VARIANTS - 1}"
    # Reproducible across calls.
    v2 = variants_for_scheme("random")
    assert v1 == v2
    for _, w in v1:
        assert abs(sum(w.values()) - 1.0) < 1e-9
        assert all(w[k] > 0 for k in DIMENSIONS)
    # Independent stream: the global RNG state is never touched.
    state = random.getstate()
    variants_for_scheme("random")
    assert random.getstate() == state


def test_variants_unknown_scheme_raises():
    try:
        variants_for_scheme("bogus")
    except ValueError:
        pass
    else:
        raise AssertionError("unknown scheme should raise ValueError")


# ── weighted_cosine_similarity 的 weights 覆盖 ────────────────────────


def _toy_vectors():
    """Two vectors: identical word-length dist, orthogonal function words."""
    fv_a = FeatureVector(word_length_dist=[1.0, 0.0],
                         function_word_freq=[1.0, 0.0])
    fv_b = FeatureVector(word_length_dist=[1.0, 0.0],
                         function_word_freq=[0.0, 1.0])
    return fv_a, fv_b


def test_weighted_cosine_default_path_unchanged():
    """weights=None must equal an explicit FEATURE_WEIGHTS exactly."""
    fv_a, fv_b = _toy_vectors()
    assert (weighted_cosine_similarity(fv_a, fv_b)
            == weighted_cosine_similarity(fv_a, fv_b, FEATURE_WEIGHTS))


def test_weighted_cosine_weights_override():
    """A uniform override changes the score as hand-computed."""
    fv_a, fv_b = _toy_vectors()
    default_sim = weighted_cosine_similarity(fv_a, fv_b)
    uniform = {k: 1.0 / 8 for k in DIMENSIONS}
    uniform_sim = weighted_cosine_similarity(fv_a, fv_b, uniform)
    # Hand computation: dims score 1, 0, 0.5(empty), 0.5(empty), 1, 0.5, 1, 1.
    assert abs(uniform_sim - 5.5 / 8) < 1e-12
    assert abs(default_sim - 0.525) < 1e-12
    assert default_sim != uniform_sim
    # Iteration order of the passed dict must not matter.
    reordered = dict(reversed(list(uniform.items())))
    assert weighted_cosine_similarity(fv_a, fv_b, reordered) == uniform_sim


# ── 头条 Delta 流程与权重配置解耦 ─────────────────────────────────────


def test_delta_pipeline_sources_do_not_read_weights():
    """run_delta / stylometry / dendrogram / group_metrics never reference
    the fingerprint weight configuration."""
    for rel in ("experiments/run_delta.py",
                "core/stylometry.py",
                "viz/dendrogram.py",
                "experiments/group_metrics.py"):
        src = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        assert "FEATURE_WEIGHTS" not in src, f"{rel} reads FEATURE_WEIGHTS"
        assert "linguistic_fingerprint" not in src, \
            f"{rel} imports linguistic_fingerprint"


def test_delta_pipeline_results_immune_to_weight_changes():
    """Mutating FEATURE_WEIGHTS does not change the Delta/cluster outputs."""
    from core.stylometry import (
        build_freq_table,
        delta_matrix,
        hierarchical_cluster,
        zscore,
    )

    texts = {
        "a1": "the cat sat on the mat and the dog ran fast " * 30,
        "a2": "the dog ran and the cat slept on the warm mat " * 30,
        "b1": "alpha beta gamma delta epsilon zeta eta theta " * 30,
        "b2": "beta gamma delta alpha theta zeta epsilon eta " * 30,
    }
    labels = sorted(texts)

    def _pipeline():
        ft = build_freq_table({k: texts[k] for k in labels}, n=50)
        dm = delta_matrix(zscore(ft))
        tree = hierarchical_cluster(dm["matrix"], dm["labels"])
        return dm["matrix"], tree

    matrix_before, tree_before = _pipeline()

    saved = dict(FEATURE_WEIGHTS)
    try:
        FEATURE_WEIGHTS.update({k: 1.0 / 8 for k in FEATURE_WEIGHTS})
        matrix_after, tree_after = _pipeline()
    finally:
        FEATURE_WEIGHTS.clear()
        FEATURE_WEIGHTS.update(saved)

    assert matrix_before == matrix_after
    assert tree_before == tree_after


# ── 端到端：default 与既有输出一致；CSV 与 report 追加 ────────────────


def _build_paired_groups(root: Path, chunk_size: int) -> Path:
    """Two translator groups with matching work stems (signal-competition
    pairs) built from the synthetic sample corpus."""
    from experiments.slice_corpus import chunk_text

    mapping = {
        "translator_A": {"work1": "text_the_a.txt",
                         "work2": "text_the_b.txt"},
        "translator_B": {"work1": "text_of_a.txt",
                         "work2": "text_of_b.txt"},
    }
    inp = root / f"input_{chunk_size}"
    for group, works in mapping.items():
        gdir = inp / group
        gdir.mkdir(parents=True)
        for stem, fname in works.items():
            src = next(_SAMPLE_DIR.rglob(fname))
            text = src.read_text(encoding="utf-8")
            for k, chunk in enumerate(chunk_text(text, chunk_size), 1):
                (gdir / f"{stem}__chunk{k:03d}.txt").write_text(
                    chunk, encoding="utf-8")
    return inp


def test_default_variant_matches_run_experiment():
    """The default variant reproduces the existing fingerprint metrics
    exactly (byte-identical acceptance criterion)."""
    if not _has_matplotlib():
        print("    (skipped: matplotlib not installed)")
        return

    from experiments.run_experiment import run

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inp = _build_paired_groups(root, chunk_size=1000)

        stats = run(inp, root / "out_ref", perm_n=200)
        rows = run_sensitivity({"1k": inp}, scheme="default",
                               out_dir=root / "out_sens")

        assert len(rows) == 1
        row = rows[0]
        assert row["variant"] == "default" and row["scale"] == "1k"
        # Exact float equality: same extraction path, same conventions.
        assert row["d"] == stats["cohens_d"]
        assert row["within"] == 1.0 - stats["same_sim_mean"]
        assert row["between"] == 1.0 - stats["cross_sim_mean"]
        # Synthetic corpus separates the groups under the default weights.
        assert row["d"] > 0
        assert row["knn_acc"] >= row["knn_baseline"]


def test_run_sensitivity_csv_and_report():
    """lodo x 2 scales: 16 CSV rows; report.md is appended, never edited."""
    if not _has_matplotlib():
        print("    (skipped: matplotlib not installed)")
        return

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inp_1k = _build_paired_groups(root, chunk_size=1000)
        inp_2k = _build_paired_groups(root, chunk_size=2000)

        report = root / "report.md"
        sentinel = "# Existing Report\n\nprevious content stays.\n"
        report.write_text(sentinel, encoding="utf-8")

        rows = run_sensitivity(
            {"1k": inp_1k, "2k": inp_2k},
            scheme="lodo", out_dir=root / "out", report_path=report,
        )

        # 8 lodo variants x 2 scales.
        assert len(rows) == 16
        assert {r["scale"] for r in rows} == {"1k", "2k"}
        assert all(r["variant"].startswith("lodo_") for r in rows)
        # Matching stems across groups yield signal-competition pairs.
        assert all(r["competition_pairs"] > 0 for r in rows)

        csv_path = root / "out" / "weight_sensitivity.csv"
        assert csv_path.is_file()
        with csv_path.open(newline="", encoding="utf-8-sig") as f:
            table = list(csv.reader(f))
        assert table[0] == ["variant", "scale", "within", "between", "d",
                            "competition_wins", "knn_acc", "knn_baseline"]
        assert len(table) == 1 + 16

        # Pure append: the original bytes are an untouched prefix.
        content = report.read_text(encoding="utf-8")
        assert content.startswith(sentinel)
        assert content.count("## Weight sensitivity") == 1
        assert "decoupled" in content  # headline/weights decoupling stated


def test_all_schemes_produce_rows():
    """Every scheme evaluates cleanly on one scale (uniform + single +
    random smoke test)."""
    if not _has_matplotlib():
        print("    (skipped: matplotlib not installed)")
        return

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inp = _build_paired_groups(root, chunk_size=2000)
        expected = {"uniform": 1, "single": 8, "random": RANDOM_VARIANTS}
        for scheme, n_rows in expected.items():
            rows = run_sensitivity({"2k": inp}, scheme=scheme,
                                   out_dir=root / f"out_{scheme}")
            assert len(rows) == n_rows, f"{scheme}: {len(rows)} rows"
            assert (root / f"out_{scheme}" / "weight_sensitivity.csv").is_file()


# ── v2.3.0 返修：尺度生效性自检与 all 方案 ────────────────────────────


def _build_unbalanced_groups(root: Path, chunk_size: int) -> Path:
    """非均衡分组：translator_A 多一篇 1300 词的孤儿篇目 work3。

    各尺度的多数类比例随 tail 规则变化（1k: 7/13，2k: 5/9，4k: 2/4），
    用于验证 knn_baseline 确实按各尺度 chunk 数计算。
    """
    from experiments.slice_corpus import chunk_text

    def _read(fname: str) -> str:
        return next(_SAMPLE_DIR.rglob(fname)).read_text(encoding="utf-8")

    def _first_words(text: str, n: int) -> str:
        ends = [m.end() for m in re.finditer(r"[A-Za-z]+", text)]
        assert len(ends) >= n
        return text[: ends[n - 1]]

    mapping = {
        "translator_A": {
            "work1": _read("text_the_a.txt"),
            "work2": _read("text_the_b.txt"),
            "work3": _first_words(_read("text_the_a.txt"), 1300),
        },
        "translator_B": {
            "work1": _read("text_of_a.txt"),
            "work2": _read("text_of_b.txt"),
        },
    }
    inp = root / f"input_{chunk_size}"
    for group, works in mapping.items():
        gdir = inp / group
        gdir.mkdir(parents=True)
        for stem, text in works.items():
            for k, chunk in enumerate(chunk_text(text, chunk_size), 1):
                (gdir / f"{stem}__chunk{k:03d}.txt").write_text(
                    chunk, encoding="utf-8")
    return inp


def test_scales_produce_distinct_rows_and_true_baselines():
    """Bug-1 自检：同一变体在三档尺度上的 d 不得全部相同，且
    knn_baseline 必须等于按各尺度 chunk 数独立算出的多数类比例。"""
    if not _has_matplotlib():
        print("    (skipped: matplotlib not installed)")
        return

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inputs = {
            scale: _build_unbalanced_groups(root, size)
            for scale, size in (("1k", 1000), ("2k", 2000), ("4k", 4000))
        }

        # 独立重算各尺度多数类比例（不经过被测代码）。
        expected_baseline = {}
        for scale, inp in inputs.items():
            counts = [len(list(g.glob("*.txt")))
                      for g in inp.iterdir() if g.is_dir()]
            assert all(c >= 2 for c in counts), f"{scale}: 构造失败 {counts}"
            expected_baseline[scale] = max(counts) / sum(counts)
        # 测试数据必须让三档基线不全相同，否则自检无效。
        assert len({round(v, 9) for v in expected_baseline.values()}) > 1, \
            f"测试数据构造失败：三档基线相同 {expected_baseline}"

        rows = run_sensitivity(inputs, scheme="uniform")
        assert len(rows) == 3
        by_scale = {r["scale"]: r for r in rows}
        assert set(by_scale) == {"1k", "2k", "4k"}

        ds = {s: by_scale[s]["d"] for s in by_scale}
        assert len(set(ds.values())) > 1, f"三档 d 全部相同: {ds}"
        for s, row in by_scale.items():
            assert row["knn_baseline"] == expected_baseline[s], (
                f"{s}: baseline {row['knn_baseline']} != "
                f"真实多数类比例 {expected_baseline[s]}")


def test_duplicate_scale_dirs_rejected():
    """Bug-1 护栏：多个尺度指向同一目录会直接报错，不再静默产出
    逐字节相同的行。"""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inp = _build_paired_groups(root, chunk_size=1000)
        try:
            run_sensitivity({"1k": inp, "2k": inp})
        except ValueError as e:
            assert "same directory" in str(e)
        else:
            raise AssertionError("重复尺度目录未被拒绝")


def test_all_scheme_is_38_variants():
    """all = default + uniform + 8 lodo + 8 single + 20 random = 38 变体。"""
    variants = variants_for_scheme("all")
    assert len(variants) == 38
    names = [n for n, _ in variants]
    assert names[0] == "default" and names[1] == "uniform"
    assert sum(n.startswith("lodo_") for n in names) == 8
    assert sum(n.startswith("single_") for n in names) == 8
    assert sum(n.startswith("random_") for n in names) == RANDOM_VARIANTS
    # 与逐族拼接结果完全一致（同序同权重）。
    assert variants == (
        variants_for_scheme("default") + variants_for_scheme("uniform")
        + variants_for_scheme("lodo") + variants_for_scheme("single")
        + variants_for_scheme("random"))


def test_all_scheme_full_table_and_overwrite():
    """Bug-2 自检：all × 3 尺度 = 114 行；重复运行覆盖写，行数不增。"""
    if not _has_matplotlib():
        print("    (skipped: matplotlib not installed)")
        return

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inputs = {
            scale: _build_paired_groups(root / f"b{size}", chunk_size=size)
            for scale, size in (("1k", 1000), ("2k", 2000), ("4k", 4000))
        }
        out = root / "out"

        rows = run_sensitivity(inputs, scheme="all", out_dir=out)
        assert len(rows) == 38 * 3

        csv_path = out / "weight_sensitivity.csv"
        with csv_path.open(newline="", encoding="utf-8-sig") as f:
            table = list(csv.reader(f))
        assert len(table) == 1 + 114
        assert {r[1] for r in table[1:]} == {"1k", "2k", "4k"}
        # 每个变体族在三档都有行
        families = {"default": 1, "uniform": 1, "lodo_": 8,
                    "single_": 8, "random_": RANDOM_VARIANTS}
        for prefix, n in families.items():
            hit = [r for r in table[1:]
                   if r[0] == prefix or r[0].startswith(prefix)]
            assert len(hit) == n * 3, f"{prefix}: {len(hit)} rows"

        # 覆盖写：再跑一次（换个方案也行），CSV 不追加、行数正确。
        rows2 = run_sensitivity(inputs, scheme="all", out_dir=out)
        assert len(rows2) == 114
        with csv_path.open(newline="", encoding="utf-8-sig") as f:
            table2 = list(csv.reader(f))
        assert len(table2) == 1 + 114
