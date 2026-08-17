"""Tests for experiments/slice_corpus.py and experiments/run_experiment.py.

Compatible with ``python run_tests.py`` (plain functions, no pytest).

The full-pipeline test builds translator_A / translator_B groups from the
synthetic corpus in ``experiments/sample_corpus`` (the_a/the_b vs
of_a/of_b), whose design guarantees within-group Delta << cross-group
Delta. It is skipped when matplotlib is unavailable (dendrogram export
requires it).
"""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experiments.slice_corpus import chunk_text, slice_corpus  # noqa: E402

_WORD_RE = re.compile(r"[A-Za-z]+")
_SAMPLE_DIR = Path(__file__).resolve().parent.parent / "experiments" / "sample_corpus"


def _word_count(text: str) -> int:
    """Word count using the same regex as core.stylometry."""
    return len(_WORD_RE.findall(text))


def _make_words(n: int) -> str:
    """A text of exactly ``n`` regex-words."""
    return " ".join(f"w{i}" for i in range(n))


def test_chunk_text_word_counts():
    """Full chunks contain exactly chunk-size words."""
    chunks = chunk_text(_make_words(4500), chunk_size=2000)
    assert len(chunks) == 2, f"expected 2 chunks, got {len(chunks)}"
    for c in chunks:
        assert _word_count(c) == 2000


def test_chunk_tail_rule():
    """Tail < 0.5x chunk-size is dropped; >= 0.5x is kept."""
    assert len(chunk_text(_make_words(2500), 2000)) == 1  # 500-word tail dropped
    chunks = chunk_text(_make_words(3500), 2000)          # 1500-word tail kept
    assert len(chunks) == 2
    assert _word_count(chunks[1]) == 1500
    assert len(chunk_text(_make_words(999), 2000)) == 0   # whole text below half
    assert len(chunk_text(_make_words(1000), 2000)) == 1  # exactly half: kept
    # Boundary: tail of exactly 0.5x is kept.
    assert len(chunk_text(_make_words(3000), 2000)) == 2


def test_chunk_preserves_punctuation():
    """Chunks keep the original punctuation/whitespace (fingerprint needs it)."""
    text = "Hello, world! " * 400  # 800 words
    chunks = chunk_text(text, 200)
    assert chunks and "," in chunks[0] and "!" in chunks[0]


def test_slice_corpus_output_structure():
    """slice_corpus mirrors the directory tree and names files __chunkNNN."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inp = root / "in"
        (inp / "sub").mkdir(parents=True)
        (inp / "alpha.txt").write_text(_make_words(2500), encoding="utf-8")
        (inp / "sub" / "beta.txt").write_text(_make_words(3500), encoding="utf-8")
        out = root / "out"

        written = slice_corpus(inp, out, chunk_size=2000)

        expected = [
            out / "alpha__chunk001.txt",
            out / "sub" / "beta__chunk001.txt",
            out / "sub" / "beta__chunk002.txt",
        ]
        for p in expected:
            assert p.is_file(), f"missing output: {p}"
        assert sorted(written) == sorted(expected)
        assert _word_count((out / "alpha__chunk001.txt").read_text(encoding="utf-8")) == 2000


def _build_groups(root: Path, group_map: dict, chunk_size: int = 0) -> Path:
    """Materialize group dirs under ``root`` from ``{group: [src_filenames]}``.

    When ``chunk_size`` > 0, each source text is first sliced with
    ``chunk_text`` (simulating the real slice-then-experiment workflow).
    """
    from experiments.slice_corpus import chunk_text

    inp = root / "input"
    for group, files in group_map.items():
        gdir = inp / group
        gdir.mkdir(parents=True)
        for fname in files:
            # 文件可能位于组子目录（the/、of/）下，递归定位。
            src = next(_SAMPLE_DIR.rglob(fname))
            text = src.read_text(encoding="utf-8")
            stem = Path(fname).stem
            if chunk_size > 0:
                for k, chunk in enumerate(chunk_text(text, chunk_size), 1):
                    (gdir / f"{stem}__chunk{k:03d}.txt").write_text(
                        chunk, encoding="utf-8"
                    )
            else:
                (gdir / fname).write_text(text, encoding="utf-8")
    return inp


def test_run_experiment_full_pipeline():
    """Full grouped experiment over *sliced* samples separates the groups."""
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print("    (skipped: matplotlib not installed)")
        return

    from experiments.run_experiment import run

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inp = _build_groups(
            root,
            {
                "translator_A": ["text_the_a.txt", "text_the_b.txt"],
                "translator_B": ["text_of_a.txt", "text_of_b.txt"],
            },
            chunk_size=1000,  # 12 chunks: exercises the real sliced workflow
        )
        out = root / "out"

        stats = run(inp, out)

        # Artifacts exist.
        for name in ("delta_matrix.csv", "dendrogram.png", "report.md",
                     "fingerprint_pairs.csv"):
            assert (out / name).is_file(), f"missing artifact: {name}"

        assert stats["n_samples"] == 12

        # The synthetic corpus guarantees within-group Delta << cross-group,
        # also at slice level (see sample_corpus/_generate.py docstring).
        assert stats["within_delta_mean"] < stats["cross_delta_mean"], (
            f"within={stats['within_delta_mean']:.4f} not below "
            f"cross={stats['cross_delta_mean']:.4f}"
        )
        assert stats["same_sim_mean"] > stats["cross_sim_mean"]

        # Report contains statistics and a generated conclusion.
        report = (out / "report.md").read_text(encoding="utf-8")
        assert "Wilcoxon" in report and "Cohen's d" in report
        assert "## 结论" in report
        assert "![Dendrogram](dendrogram.png)" in report
        # Groups separated: no sanity-check warning expected.
        assert "Sanity check" not in report


def test_run_experiment_warns_without_separation():
    """Indistinguishable groups trigger the no-separation sanity warning."""
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print("    (skipped: matplotlib not installed)")
        return

    from experiments.run_experiment import run

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # Both "groups" come from the same distribution (the-group texts),
        # so cross/within Delta ratio should be ~1.
        inp = _build_groups(
            root,
            {
                "translator_A": ["text_the_a.txt"],
                "translator_B": ["text_the_b.txt"],
            },
            chunk_size=1000,
        )
        out = root / "out"

        stats = run(inp, out)

        assert stats["delta_ratio"] <= 1.1, (
            f"expected ratio <= 1.1 for same-distribution groups, "
            f"got {stats['delta_ratio']:.3f}"
        )
        report = (out / "report.md").read_text(encoding="utf-8")
        assert "Sanity check" in report


def test_run_experiment_returns_result_dict():
    """run() 可作为库函数被外部（如 GUI）调用，返回结构化结果字典。"""
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print("    (skipped: matplotlib not installed)")
        return

    from experiments.run_experiment import run

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inp = _build_groups(
            root,
            {
                "translator_A": ["text_the_a.txt", "text_the_b.txt"],
                "translator_B": ["text_of_a.txt", "text_of_b.txt"],
            },
        )
        out = root / "out"

        stats = run(inp, out, perm_n=200)

        # 结果字典包含 GUI 摘要所需的全部字段。
        expected_keys = {
            "groups", "n_samples",
            "within_delta_mean", "cross_delta_mean",
            "delta_diff", "delta_ratio",
            "same_sim_mean", "cross_sim_mean",
            "p_wilcoxon", "p_permutation", "cohens_d",
            "significant", "conclusion",
        }
        missing = expected_keys - set(stats)
        assert not missing, f"result dict missing keys: {missing}"

        assert stats["groups"] == {"translator_A": 2, "translator_B": 2}
        assert stats["n_samples"] == 4
        for key in ("within_delta_mean", "cross_delta_mean", "delta_diff",
                    "same_sim_mean", "cross_sim_mean",
                    "p_wilcoxon", "p_permutation", "cohens_d"):
            assert isinstance(stats[key], float), f"{key} is not a float"
        assert isinstance(stats["significant"], bool)
        assert isinstance(stats["conclusion"], str) and stats["conclusion"]

        # 输出工件与命令行方式一致。
        for name in ("delta_matrix.csv", "dendrogram.png",
                     "fingerprint_pairs.csv", "report.md"):
            assert (out / name).is_file(), f"missing artifact: {name}"
