"""experiments/run_delta.py 最小冒烟测试。

临时目录构造小语料跑通 main()，断言 delta_matrix.csv 产出且非空；
同时验证 DeprecationWarning 已接入。无 matplotlib 时跳过
（dendrogram.png 依赖它）。
"""

import sys
import tempfile
import warnings
from pathlib import Path

from tests import has_matplotlib


def test_run_delta_smoke():
    if not has_matplotlib():
        return

    from experiments import run_delta

    with tempfile.TemporaryDirectory() as tmp:
        in_dir = Path(tmp) / "corpus"
        out_dir = Path(tmp) / "out"
        in_dir.mkdir()
        (in_dir / "author_a.txt").write_text(
            "the quick brown fox jumps over the lazy dog. " * 60,
            encoding="utf-8",
        )
        (in_dir / "author_b.txt").write_text(
            "of course it was one of those things, one of them all. " * 60,
            encoding="utf-8",
        )

        old_argv = sys.argv
        sys.argv = [
            "run_delta.py", "--input", str(in_dir), "--out", str(out_dir),
        ]
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                run_delta.main()
            assert any(
                issubclass(w.category, DeprecationWarning) for w in caught
            ), "main() 应发出 DeprecationWarning"
        finally:
            sys.argv = old_argv

        csv_path = out_dir / "delta_matrix.csv"
        assert csv_path.exists(), "delta_matrix.csv 未产出"
        content = csv_path.read_text(encoding="utf-8").strip()
        assert content, "delta_matrix.csv 为空"
        # 2 个文本 → 表头 + 2 行
        assert len(content.splitlines()) == 3
