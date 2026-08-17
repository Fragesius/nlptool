"""进度系统测试（v2.0.0 阶段三）。

验证 run()/slice_corpus() 的 progress_callback：
- 各阶段 total 与实际工作量吻合（Delta 矩阵 N²/2、特征提取 N、
  指纹配对 M、1-NN N、信号竞争 P、切片文件数）；
- 每阶段 current 单调递增至 total；
- 不传回调时行为不变（既有测试已全部覆盖无回调路径）。

Compatible with ``python run_tests.py`` (plain functions, no pytest).
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.test_group_metrics import _build_paired_groups  # noqa: E402


def test_run_progress_callback_stage_totals():
    """12 样本（2 组 × 2 篇 × 3 切片）下各阶段进度总量精确吻合。"""
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print("    (skipped: matplotlib not installed)")
        return

    from experiments.run_experiment import run

    events = []  # (stage, current, total)

    def cb(current, total, stage):
        events.append((stage, current, total))

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inp = _build_paired_groups(root)
        stats = run(inp, root / "out", perm_n=100, progress_callback=cb)

    n = stats["n_samples"]  # 12
    assert n == 12

    # 按阶段汇总
    by_stage: dict = {}
    for stage, current, total in events:
        by_stage.setdefault(stage, []).append((current, total))

    # 关键阶段必须出现且总量正确
    expected_totals = {
        "Delta 矩阵": n * (n - 1) // 2,      # 66
        "指纹特征提取": n,                     # 12
        "指纹配对": n * (n - 1) // 2,         # 66
        "1-NN 最近邻": n,                     # 12
        "信号竞争": 2,                         # ah_q / kong_yiji 两对篇目
    }
    for stage, total in expected_totals.items():
        assert stage in by_stage, f"缺少进度阶段: {stage}"
        evs = by_stage[stage]
        # 每次上报的 total 一致且正确
        assert all(t == total for _, t in evs), (
            f"{stage} total 应为 {total}: {evs[:3]}..."
        )
        # current 单调递增且最终到达 total
        currents = [c for c, _ in evs]
        assert currents == sorted(currents), f"{stage} current 非单调"
        assert currents[-1] == total, f"{stage} 未走到 {total}"


def test_slice_corpus_progress_callback():
    """切片阶段进度：total == 源文件数，逐文件递增。"""
    from experiments.slice_corpus import slice_corpus

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inp = root / "in"
        (inp / "sub").mkdir(parents=True)
        words = " ".join(f"w{i}" for i in range(1200))
        (inp / "a.txt").write_text(words, encoding="utf-8")
        (inp / "sub" / "b.txt").write_text(words, encoding="utf-8")

        events = []
        written = slice_corpus(
            inp, root / "out", chunk_size=1000,
            progress_callback=lambda c, t, s: events.append((s, c, t)),
        )

    assert written, "应有切片产出"
    assert [e[0] for e in events] == ["切片", "切片"]
    assert [(c, t) for _, c, t in events] == [(1, 2), (2, 2)]


def test_run_without_callback_unchanged():
    """不传回调时 run() 正常完成（命令行路径行为不变）。"""
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print("    (skipped: matplotlib not installed)")
        return

    from experiments.run_experiment import run

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inp = _build_paired_groups(root)
        stats = run(inp, root / "out", perm_n=100)
        assert stats["n_samples"] == 12
        assert (root / "out" / "report.md").is_file()
