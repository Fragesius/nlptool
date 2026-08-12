"""树状图（dendrogram）绘制：Burrows' Delta 层次聚类结果可视化。

不依赖 scipy，根据 ``core.stylometry.hierarchical_cluster`` 返回的
嵌套 dict 树结构用 matplotlib 手绘。叶子标签为文本名，横向布局
（文本名在纵轴、合并距离在横轴），300 dpi 导出 PNG。
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
    title: str = "Burrows' Delta 层次聚类树状图",
) -> Path:
    """绘制层次聚类树状图并保存为 PNG（300 dpi）。

    横向布局：叶子文本名沿纵轴均匀排列，横轴为合并距离（Delta）。

    :param tree: ``hierarchical_cluster`` 返回的根节点
    :param out_path: 输出 PNG 路径
    :param title: 图标题
    :return: 实际保存的文件路径
    """
    leaves = _collect_leaves(tree)
    n = len(leaves)
    y_of = {id(leaf): n - 1 - i for i, leaf in enumerate(leaves)}

    fig_width = max(6.0, 4.0 + 0.4 * max(len(str(l["label"])) for l in leaves))
    fig_height = max(3.0, 0.6 * n + 1.5)
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))

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

    ax.set_yticks([y_of[id(leaf)] for leaf in leaves])
    ax.set_yticklabels([str(leaf["label"]) for leaf in leaves])
    ax.set_xlabel("合并距离（Burrows' Delta）")
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
