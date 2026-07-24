"""可视化模块：词云、词频柱状图、依存句法图、情感趋势图。

所有绘图返回 matplotlib ``Figure``，由界面用 ``FigureCanvasTkAgg`` 嵌入。
支持浅色/深色主题自动适配。
"""

from __future__ import annotations

import os
from collections import Counter
from typing import List, Optional

# matplotlib 后端配置（必须在 pyplot 之前设置）
import matplotlib

matplotlib.use("TkAgg")
import matplotlib.pyplot as plt  # noqa: E402

from core.analyzer import (  # noqa: E402
    BasicResult,
    SyntaxResult,
    split_sentences,
    sentiment,
    detect_language,
    tokenize,
)
from core.linguistic_fingerprint import (  # noqa: E402
    SimilarityResult,
)

# --------------------------------------------------------------------------- #
# 中文字体
# --------------------------------------------------------------------------- #

_CJK_FONTS = [
    "Microsoft YaHei",
    "SimHei",
    "SimSun",
    "Noto Sans CJK SC",
    "PingFang SC",
    "Arial Unicode MS",
]
_FONT_PATH_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]


def _resolve_cjk_font_path() -> Optional[str]:
    for p in _FONT_PATH_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def configure_fonts() -> None:
    """配置 matplotlib 以正确显示中文。"""
    plt.rcParams["axes.unicode_minus"] = False
    for f in _CJK_FONTS:
        try:
            plt.rcParams["font.sans-serif"] = [f] + plt.rcParams.get("font.sans-serif", [])
            return
        except Exception:
            continue


configure_fonts()


# --------------------------------------------------------------------------- #
# 深色模式辅助
# --------------------------------------------------------------------------- #

# 深色主题 matplotlib 配色
_DARK_BG = "#141529"
_DARK_AXES_BG = "#1e2038"
_DARK_TEXT = "#e2e4f0"
_DARK_GRID = "#2d3050"


def _apply_dark_theme(fig, ax, title: str) -> None:
    """对已创建的 figure/axes 应用深色主题。"""
    fig.patch.set_facecolor(_DARK_BG)
    ax.set_facecolor(_DARK_AXES_BG)
    ax.title.set_color(_DARK_TEXT)
    ax.xaxis.label.set_color(_DARK_TEXT)
    ax.yaxis.label.set_color(_DARK_TEXT)
    ax.tick_params(colors=_DARK_TEXT)
    ax.spines["bottom"].set_color(_DARK_GRID)
    ax.spines["top"].set_color(_DARK_GRID)
    ax.spines["left"].set_color(_DARK_GRID)
    ax.spines["right"].set_color(_DARK_GRID)
    ax.grid(color=_DARK_GRID, alpha=0.3)


def _lighten_color(hex_color: str, factor: float = 1.3) -> str:
    """将 hex 颜色调亮以便在深色背景上可见。"""
    hex_color = hex_color.lstrip("#")
    r, g, b = tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    r = min(255, int(r * factor))
    g = min(255, int(g * factor))
    b = min(255, int(b * factor))
    return f"#{r:02x}{g:02x}{b:02x}"


# --------------------------------------------------------------------------- #
# 词云
# --------------------------------------------------------------------------- #


def make_wordcloud(freq: Counter, title: str = "词云", dark_mode: bool = False) -> "plt.Figure":
    try:
        from wordcloud import WordCloud
    except ImportError:
        return _fallback_fig(title, "未安装 wordcloud 库，无法生成词云。\n请 pip install wordcloud", dark_mode)

    font_path = _resolve_cjk_font_path()
    freq_dict = dict(freq)
    if not freq_dict:
        return _fallback_fig(title, "无可用词汇。", dark_mode)

    bg = _DARK_BG if dark_mode else "white"
    cmap = "plasma" if dark_mode else "viridis"

    wc = WordCloud(
        font_path=font_path,
        width=800,
        height=450,
        background_color=bg,
        max_words=120,
        colormap=cmap,
    ).generate_from_frequencies(freq_dict)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    ax.set_title(title, color=_DARK_TEXT if dark_mode else "#1f2733", fontsize=14)
    if dark_mode:
        fig.patch.set_facecolor(_DARK_BG)
    return fig


# --------------------------------------------------------------------------- #
# 词频柱状图
# --------------------------------------------------------------------------- #


def make_freq_bar(freq: Counter, topk: int = 20, title: str = "高频词",
                  dark_mode: bool = False) -> "plt.Figure":
    items = freq.most_common(topk)
    if not items:
        return _fallback_fig(title, "无可用词汇。", dark_mode)
    words, counts = zip(*items)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    bar_color = "#7b8cff" if dark_mode else "#4C78A8"
    ax.bar(range(len(words)), counts, color=bar_color, alpha=0.88)
    ax.set_xticks(range(len(words)))
    ax.set_xticklabels(words, rotation=45, ha="right")
    ax.set_ylabel("频次")
    ax.set_title(title)

    if dark_mode:
        _apply_dark_theme(fig, ax, title)
    else:
        fig.tight_layout()
    return fig


# --------------------------------------------------------------------------- #
# 词性分布饼图
# --------------------------------------------------------------------------- #


def make_pos_pie(pos_dist: Counter, title: str = "词性分布",
                 dark_mode: bool = False) -> "plt.Figure":
    items = pos_dist.most_common(8)
    if not items:
        return _fallback_fig(title, "无词性数据。", dark_mode)
    labels, sizes = zip(*items)

    # 深色模式下使用更鲜艳的配色
    if dark_mode:
        colors = plt.cm.Set3(range(len(labels)))
    else:
        colors = None

    fig, ax = plt.subplots(figsize=(6, 4.5))
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, autopct="%1.1f%%",
        startangle=140, colors=colors,
    )
    ax.set_title(title)
    ax.axis("equal")

    if dark_mode:
        _apply_dark_theme(fig, ax, title)
        # 深色下调整饼图文字颜色
        for t in texts:
            t.set_color(_DARK_TEXT)
        for at in autotexts:
            at.set_color("#ffffff")
    return fig


# --------------------------------------------------------------------------- #
# 依存句法可视化
# --------------------------------------------------------------------------- #


def make_dependency_graph(deps: List[dict], title: str = "依存句法",
                          dark_mode: bool = False) -> "plt.Figure":
    """绘制依存句法树。

    将 spaCy 的扁平依存关系渲染为分层弧形图：
    - 词在底部排成一行，词性标注在下方
    - 依存弧按跨度分层叠放，避免重叠
    - ROOT 词上方标注「ROOT」
    - 超过 30 个词的句子自动缩小字号

    修复要点（对比旧版）：
    - 用 token 序号代替 text 做键，消除重复词导致的弧指向错误
    - 弧的垂直位置按跨度分配层级，短弧在下、长弧在上
    - 字号随句长自适应缩放
    """
    if not deps:
        return _fallback_fig(title, "无依存数据（需安装 spaCy 英文/中文模型）。", dark_mode)

    n = len(deps)
    # 字宽自适应：短句 0.65 英寸/词，长句收窄
    if n <= 10:
        w_per_word = 0.65
        word_fs = 11
        pos_fs = 8
        dep_fs = 7
    elif n <= 20:
        w_per_word = 0.55
        word_fs = 10
        pos_fs = 7
        dep_fs = 6.5
    elif n <= 30:
        w_per_word = 0.45
        word_fs = 9
        pos_fs = 6.5
        dep_fs = 6
    else:
        w_per_word = 0.38
        word_fs = 8
        pos_fs = 6
        dep_fs = 5.5

    # 计算弧所需的最大层级数（用于确定图高）
    arcs_data = []  # [(child_idx, head_idx, dep_label, span_distance)]
    for i, d in enumerate(deps):
        if d["dep"] == "ROOT":
            continue
        # 用序号定位 head（消除重复词 bug）
        head_idx = _find_head_index(deps, i, d)
        if head_idx is None or head_idx == i:
            continue
        span = abs(i - head_idx)
        arcs_data.append((i, head_idx, d["dep"], span))

    # 按跨度排序：短弧在下
    arcs_data.sort(key=lambda a: a[3])

    # 贪心分配层级：每条弧放在第一个不冲突的层，短弧优先
    layers = []  # layers[k] = [(left, right), ...]
    arc_layer = {}  # arc_index -> layer
    for ai, (child, head, label, span) in enumerate(arcs_data):
        lo, hi = (child, head) if child < head else (head, child)
        assigned = -1
        for lv, occupied in enumerate(layers):
            if all(hi < o_lo or lo > o_hi for o_lo, o_hi in occupied):
                assigned = lv
                occupied.append((lo, hi))
                break
        if assigned < 0:
            assigned = len(layers)
            layers.append([(lo, hi)])
        arc_layer[ai] = assigned

    n_layers = len(layers)
    fig_h = 2.0 + n_layers * 0.55
    fig_w = max(6, n * w_per_word + 1.2)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    # 颜色
    text_color = _DARK_TEXT if dark_mode else "#1f2733"
    muted_color = _DARK_GRID if dark_mode else "#6b6b6b"
    root_color = "#7b8cff" if dark_mode else "#4C78A8"
    # 为不同层级使用不同颜色的弧
    arc_palette = ["#E45756", "#F58518", "#54A24B", "#4C78A8", "#B279A2",
                   "#72B7B2", "#EECA3B", "#BAB0AC"]
    if dark_mode:
        arc_palette = ["#f48fb1", "#ffab40", "#81c784", "#7b8cff", "#ce93d8",
                       "#80cbc4", "#fff176", "#bcaaa4"]

    # ── 画词 ──
    for i, d in enumerate(deps):
        ax.text(i, 0, d["text"], ha="center", va="center",
                fontsize=word_fs, fontweight="bold", color=text_color)
        ax.text(i, -0.38, d["pos"], ha="center", va="center",
                fontsize=pos_fs, color=muted_color)
        if d["dep"] == "ROOT":
            ax.text(i, 0.35, "ROOT", ha="center",
                    fontsize=min(8, pos_fs + 1), fontweight="bold",
                    color=root_color, bbox=dict(
                        boxstyle="round,pad=0.15", fc="none",
                        ec=root_color, lw=1.2, alpha=0.7))

    # ── 画弧 ──
    arc_bottom = 0.22   # 最底层弧的起始 y
    layer_gap = 0.5     # 层间距

    for ai, (child, head, label, span) in enumerate(arcs_data):
        lv = arc_layer[ai]
        base_y = arc_bottom + lv * layer_gap
        color = arc_palette[lv % len(arc_palette)]

        # 跨度越大弧度越大
        rad = 0.15 + span * 0.018
        if head < child:
            rad = -rad

        mid = (child + head) / 2.0
        ax.annotate(
            "",
            xy=(head, base_y),
            xytext=(child, base_y),
            arrowprops=dict(
                arrowstyle="->", lw=1.3,
                color=color,
                connectionstyle=f"arc3,rad={rad}",
            ),
        )
        # 标签放在弧顶点附近
        label_y = base_y + abs(rad) * 0.7 + 0.12
        ax.text(mid, label_y, label, ha="center", fontsize=dep_fs,
                color=color, style="italic",
                bbox=dict(boxstyle="round,pad=0.1", fc="white" if not dark_mode else _DARK_BG,
                          ec="none", alpha=0.75))

    # ── 边界 ──
    ax.set_ylim(-0.55, arc_bottom + n_layers * layer_gap + 0.15)
    ax.set_xlim(-0.8, n - 0.2)
    ax.axis("off")
    ax.set_title(title, color=text_color, fontsize=13, fontweight="bold", pad=6)

    if dark_mode:
        fig.patch.set_facecolor(_DARK_BG)
        ax.set_facecolor(_DARK_AXES_BG)
    else:
        fig.tight_layout(pad=1.0)
    return fig


def _find_head_index(deps: List[dict], child_idx: int, dep_entry: dict) -> Optional[int]:
    """根据 dep dict 找到 head token 的序号。

    策略：先按序号匹配（如果 spaCy token 保留了序号），
    再按 text 精确匹配；若出现多次则选离 child 最近的那个。
    这消除了旧版 text_to_x dict 中重复词覆盖导致的指向错误。
    """
    head_text = dep_entry.get("head_text", "")
    # 尝试序号字段（如果 dependencies 函数保留了 i 属性）
    head_i = dep_entry.get("head_i")
    if head_i is not None and 0 <= head_i < len(deps):
        return head_i

    # Fallback：按文本匹配，选离 child 最近的
    candidates = []
    for i, d in enumerate(deps):
        if d["text"] == head_text:
            candidates.append(i)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    # 选离 child 最近的
    return min(candidates, key=lambda i: abs(i - child_idx))


# --------------------------------------------------------------------------- #
# 情感趋势图
# --------------------------------------------------------------------------- #


def make_sentiment_trend(text: str, lang: Optional[str] = None,
                         title: str = "情感趋势", dark_mode: bool = False) -> "plt.Figure":
    sents = split_sentences(text)
    if not sents:
        return _fallback_fig(title, "无句子。", dark_mode)

    scores = []
    for s_text in sents:
        s_lang = lang or detect_language(s_text)
        sc = sentiment(s_text, s_lang)["score"]
        scores.append(sc)

    fig, ax = plt.subplots(figsize=(8, 4))
    xs = list(range(1, len(scores) + 1))

    if dark_mode:
        colors = ["#4ade80" if v > 0.15 else "#f87171" if v < -0.15 else "#8b8fa8" for v in scores]
    else:
        colors = ["#54A24B" if v > 0.15 else "#E45756" if v < -0.15 else "#BAB0AC" for v in scores]

    ax.bar(xs, scores, color=colors, alpha=0.88)
    zero_color = _DARK_GRID if dark_mode else "black"
    ax.axhline(0, color=zero_color, linewidth=0.8)
    ax.set_xlabel("句子序号")
    ax.set_ylabel("情感得分")
    ax.set_title(title)
    ax.set_xticks(xs)

    if dark_mode:
        _apply_dark_theme(fig, ax, title)
    else:
        fig.tight_layout()
    return fig


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #


def _fallback_fig(title: str, msg: str, dark_mode: bool = False) -> "plt.Figure":
    text_color = _DARK_TEXT if dark_mode else "#1f2733"
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.text(0.5, 0.5, msg, ha="center", va="center", fontsize=11, wrap=True, color=text_color)
    ax.set_title(title, color=text_color)
    ax.axis("off")
    if dark_mode:
        fig.patch.set_facecolor(_DARK_BG)
        ax.set_facecolor(_DARK_AXES_BG)
    return fig


# --------------------------------------------------------------------------- #
# 语言指纹分析
# --------------------------------------------------------------------------- #


def make_fingerprint_bar(
    sim_b: "SimilarityResult",
    sim_controls: "List[SimilarityResult]",
    p_value: float,
    cohens_d: float,
    verdict: str,
    dark_mode: bool = False,
) -> "plt.Figure":
    """语言指纹相似度对比柱状图。

    Args:
        sim_b: A vs 嫌疑作者 B 的相似度结果。
        sim_controls: A vs 各对照作者的相似度列表。
        p_value: Wilcoxon p 值。
        cohens_d: 效应量。
        verdict: 结论文字（"支持" / "弱支持" / "不确定"）。
        dark_mode: 深色主题。
    """
    from core.linguistic_fingerprint import SimilarityResult  # noqa: F811

    labels: List[str] = ["A vs 嫌疑作者 B"]
    means: List[float] = [sim_b.mean_similarity]
    stds: List[float] = [sim_b.std_similarity]
    colors: List[str] = []

    accent = "#7b8cff" if dark_mode else "#2f6fed"
    muted_gray = "#6b7480" if dark_mode else "#9aa0ac"
    colors.append(accent)

    for sc in sim_controls:
        labels.append(f"A vs 对照 {sc.ref_label}")
        means.append(sc.mean_similarity)
        stds.append(sc.std_similarity)
        colors.append(muted_gray)

    fig, ax = plt.subplots(figsize=(8, 5))
    x_pos = range(len(labels))
    bars = ax.bar(x_pos, means, yerr=stds, capsize=8, color=colors,
                  edgecolor="none", alpha=0.9, width=0.55)

    ax.set_xticks(list(x_pos))
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel("余弦相似度", fontsize=10)
    ax.set_ylim(0, min(1.0, max(means) * 1.3 + 0.1))
    ax.set_title("语言指纹相似度对比", fontsize=13, fontweight="bold")

    for bar, mv in zip(bars, means):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                f"{mv:.3f}", ha="center", va="bottom", fontsize=9)

    info_lines = [
        f"Wilcoxon p = {p_value:.4f}",
        f"Cohen's d = {cohens_d:.3f}",
        f"结论: {verdict}",
    ]
    info_text = "\n".join(info_lines)
    text_color = _DARK_TEXT if dark_mode else "#1f2733"
    box_color = _DARK_AXES_BG if dark_mode else "#f4f6fb"
    ax.text(0.02, 0.97, info_text, transform=ax.transAxes,
            fontsize=9, verticalalignment="top", fontfamily="monospace",
            bbox=dict(boxstyle="round,pad=0.5", facecolor=box_color,
                       edgecolor=accent, alpha=0.9),
            color=text_color)

    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()

    if dark_mode:
        _apply_dark_theme(fig, ax, "")

    return fig
