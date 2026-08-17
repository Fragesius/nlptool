"""Tests for the v2.1.0 report-language parameter and CLI English output.

Compatible with ``python run_tests.py`` (plain functions, no pytest).
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_ROOT = Path(__file__).resolve().parent.parent
_CJK_RE = re.compile(r"[一-鿿]")

_GROUP_MAP = {
    "translator_A": ["text_the_a.txt", "text_the_b.txt"],
    "translator_B": ["text_of_a.txt", "text_of_b.txt"],
}


def _matplotlib_available() -> bool:
    try:
        import matplotlib  # noqa: F401
        return True
    except ImportError:
        return False


def _run_experiment(out: Path, **kwargs):
    from experiments.run_experiment import run
    from tests.test_experiment import _build_groups

    with tempfile.TemporaryDirectory() as td:
        inp = _build_groups(Path(td), _GROUP_MAP)
        return run(inp, out, perm_n=200, **kwargs)


def test_report_lang_en_contains_no_chinese():
    """--report-lang en: report.md must not contain any CJK characters."""
    if not _matplotlib_available():
        print("    (skipped: matplotlib not installed)")
        return

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "out"
        _run_experiment(out, report_lang="en")
        report = (out / "report.md").read_text(encoding="utf-8")
        assert "## Conclusion" in report
        assert not _CJK_RE.search(report), (
            "en report contains Chinese: "
            + repr(_CJK_RE.search(report).group(0))
        )


def test_report_lang_default_matches_explicit_zh():
    """Default (zh) report.md is byte-identical to --report-lang zh,
    and keeps the v2.0.0 Chinese section heading."""
    if not _matplotlib_available():
        print("    (skipped: matplotlib not installed)")
        return

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        out_default = root / "out_default"
        out_zh = root / "out_zh"
        stats = _run_experiment(out_default)
        _run_experiment(out_zh, report_lang="zh")

        a = (out_default / "report.md").read_bytes()
        b = (out_zh / "report.md").read_bytes()
        assert a == b, "default report differs from --report-lang zh"
        assert "## 结论".encode("utf-8") in a
        # Returned conclusion strings stay Chinese for the GUI.
        assert _CJK_RE.search(stats["conclusion"])
        assert _CJK_RE.search(stats["nn_conclusion"])
        assert _CJK_RE.search(stats["sc_conclusion"])


def test_report_lang_en_numeric_outputs_unchanged():
    """report-lang only affects template text: CSVs and key stats are
    identical between zh and en runs."""
    if not _matplotlib_available():
        print("    (skipped: matplotlib not installed)")
        return

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        out_zh = root / "out_zh"
        out_en = root / "out_en"
        stats_zh = _run_experiment(out_zh, report_lang="zh")
        stats_en = _run_experiment(out_en, report_lang="en")

        for name in ("delta_matrix.csv", "fingerprint_pairs.csv",
                     "nn_predictions.csv", "signal_competition.csv"):
            assert (out_zh / name).read_bytes() == (out_en / name).read_bytes(), \
                f"{name} differs between zh and en"

        for key in ("within_delta_mean", "cross_delta_mean", "delta_ratio",
                    "nn_accuracy", "same_sim_mean", "cross_sim_mean",
                    "p_wilcoxon", "p_permutation", "cohens_d"):
            assert stats_zh[key] == stats_en[key], f"{key} differs"


def _check_help_english(script: str) -> None:
    proc = subprocess.run(
        [sys.executable, str(_ROOT / "experiments" / script), "--help"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, f"{script} --help exited {proc.returncode}"
    out = proc.stdout + proc.stderr
    assert out.strip(), f"{script} --help produced no output"
    assert not _CJK_RE.search(out), f"{script} --help contains Chinese"


def test_cli_help_english_slice_corpus():
    _check_help_english("slice_corpus.py")


def test_cli_help_english_run_experiment():
    _check_help_english("run_experiment.py")


def test_cli_help_english_run_delta():
    _check_help_english("run_delta.py")
