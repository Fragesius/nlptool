"""树状图（dendrogram）绘制：Burrows' Delta 层次聚类结果可视化。

不依赖 scipy，根据 ``core.stylometry.hierarchical_cluster`` 返回的
嵌套 dict 树结构用 matplotlib 手绘。叶子标签为文本名，横向布局
（文本名在纵轴、合并距离在横轴），300 dpi 导出 PNG。画布高度随
叶片数自适应（高 = max(4, 0.16 × 叶片数) 英寸，宽 7 英寸）；
叶片 > 40 时叶标签字号降为 7pt。

命令行用法（由既有 delta_matrix.csv 重建聚类出图）::

    python viz/dendrogram.py --delta delta_matrix.csv --out dendrogram.png \
        [--label-map labels.csv] [--title T]

``--label-map`` 为两列 CSV（原标签,新标签），把叶标签映射为英文
标题；不提供时行为与现状完全一致。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

# matplotlib 后端配置（必须在 pyplot 之前设置）
# 树状图用于命令行导出，默认使用无界面的 Agg 后端；
# 若上层（GUI）已设置 MPLBACKEND 则尊重之
import matplotlib

if not os.environ.get("MPLBACKEND"):
    matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

# --------------------------------------------------------------------------- #
# 中文字体（标题/轴标签含中文时避免豆腐块）
# --------------------------------------------------------------------------- #
_CJK_FONTS = [
    "Microsoft YaHei",
    "SimHei",
    "SimSun",
    "Noto Sans CJK SC",
    "PingFang SC",
    "Arial Unicode MS",
]


def _setup_cjk_font() -> None:
    """从候选中挑一个系统里真实存在的中文字体。"""
    available = {f.name for f in font_manager.fontManager.ttflist}
    for name in _CJK_FONTS:
        if name in available:
            plt.rcParams["font.sans-serif"] = [name, "DejaVu Sans"]
            break
    plt.rcParams["axes.unicode_minus"] = False


_setup_cjk_font()


def _collect_leaves(node: Dict[str, object]) -> List[Dict[str, object]]:
    """按树的中序（左、右）收集叶子节点，决定标签排列顺序。"""
    if node["left"] is None and node["right"] is None:
        return [node]
    leaves: List[Dict[str, object]] = []
    leaves.extend(_collect_leaves(node["left"]))  # type: ignore[arg-type]
    leaves.extend(_collect_leaves(node["right"]))  # type: ignore[arg-type]
    return leaves


def plot_dendrogram(
    tree: Dict[str, object],
    out_path: Union[str, Path],
    title: str = "Burrows' Delta Hierarchical Clustering",
    label_map: Optional[Dict[str, str]] = None,
) -> Path:
    """绘制层次聚类树状图并保存为 PNG（300 dpi）。

    横向布局：叶子文本名沿纵轴均匀排列，横轴为合并距离（Delta）。
    画布高度随叶片数自适应：高 = max(4, 0.16 × 叶片数) 英寸，宽 7
    英寸；叶片 > 40 时叶标签字号降为 7pt。

    :param tree: ``hierarchical_cluster`` 返回的根节点
    :param out_path: 输出 PNG 路径
    :param title: 图标题
    :param label_map: 可选的叶标签映射 ``{原标签: 新标签}``（如映射为
        英文标题）；未出现在映射中的标签保持原样。不提供时行为与
        现状完全一致。
    :return: 实际保存的文件路径
    """
    leaves = _collect_leaves(tree)
    n = len(leaves)
    y_of = {id(leaf): n - 1 - i for i, leaf in enumerate(leaves)}

    fig, ax = plt.subplots(figsize=(7.0, max(4.0, 0.16 * n)))

    def draw(node: Dict[str, object]) -> Tuple[float, float]:
        """递归绘制节点，返回该节点 (合并距离, 纵坐标)。"""
        if node["left"] is None and node["right"] is None:
            return 0.0, float(y_of[id(node)])
        left: Dict[str, object] = node["left"]  # type: ignore[assignment]
        right: Dict[str, object] = node["right"]  # type: ignore[assignment]
        lx, ly = draw(left)
        rx, ry = draw(right)
        h = float(node["height"])
        cy = (ly + ry) / 2.0
        # 左、右子树从各自高度垂直连到合并高度
        ax.plot([lx, h], [ly, ly], color="C0", lw=1.5)
        ax.plot([rx, h], [ry, ry], color="C0", lw=1.5)
        ax.plot([h, h], [ly, ry], color="C0", lw=1.5)
        return h, cy

    max_h = float(tree["height"])
    draw(tree)

    def _label(leaf: Dict[str, object]) -> str:
        text = str(leaf["label"])
        return label_map.get(text, text) if label_map else text

    ax.set_yticks([y_of[id(leaf)] for leaf in leaves])
    ticklabels = ax.set_yticklabels([_label(leaf) for leaf in leaves])
    if n > 40:
        for tl in ticklabels:
            tl.set_fontsize(7)
    ax.set_xlabel("Merge distance (Burrows' Delta)")
    ax.set_title(title)
    ax.set_xlim(left=0.0, right=max_h * 1.05 + 1e-12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    return out_path


def load_label_map(csv_path: Union[str, Path]) -> Dict[str, str]:
    """读取 ``--label-map`` CSV（两列：原标签,新标签，首行为表头）。

    :param csv_path: 标签映射 CSV 路径（utf-8 / utf-8-sig）
    :return: ``{原标签: 新标签}``；新标签为空的行被忽略
    """
    import csv

    mapping: Dict[str, str] = {}
    with Path(csv_path).open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)
    for row in rows[1:]:  # 跳过表头
        if len(row) >= 2 and row[0] and row[1]:
            mapping[row[0]] = row[1]
    return mapping


def main() -> None:
    """命令行入口：由 delta_matrix.csv 重建聚类并绘制树状图。

    用法::

        python viz/dendrogram.py --delta delta_matrix.csv \
            --out dendrogram.png [--label-map labels.csv] [--title T]
    """
    import argparse
    import csv
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from core.stylometry import hierarchical_cluster  # noqa: E402

    parser = argparse.ArgumentParser(
        description="Plot a dendrogram from an existing delta_matrix.csv")
    parser.add_argument("--delta", required=True,
                        help="delta_matrix.csv produced by run_experiment")
    parser.add_argument("--out", required=True, help="output PNG path")
    parser.add_argument("--title",
                        default="Burrows' Delta Hierarchical Clustering",
                        help="figure title")
    parser.add_argument("--label-map", default=None,
                        help="optional CSV (原标签,新标签) mapping leaf "
                             "labels to display labels, e.g. English titles")
    args = parser.parse_args()

    with Path(args.delta).open("r", newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    labels = [row[0] for row in rows[1:]]
    matrix = [[float(v) for v in row[1:]] for row in rows[1:]]

    label_map = load_label_map(args.label_map) if args.label_map else None
    tree = hierarchical_cluster(matrix, labels)
    out = plot_dendrogram(tree, args.out, title=args.title,
                          label_map=label_map)
    print(f"Dendrogram saved: {out}")


if __name__ == "__main__":
    main()
