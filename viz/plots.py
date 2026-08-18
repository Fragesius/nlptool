"""可视化模块：词云、词频柱状图、依存句法图、情感趋势图。

所有绘图返回 matplotlib ``Figure``，由界面用 ``FigureCanvasTkAgg`` 嵌入。
支持浅色/深色主题自动适配。
"""

from __future__ import annotations

import os
from collections import Counter
from typing import List, Optional

# matplotlib 后端配置（必须在 pyplot 之前设置）
# 优先尊重环境变量 MPLBACKEND；默认使用 TkAgg 以适配 Tk GUI 嵌入
import matplotlib

if not os.environ.get("MPLBACKEND"):
    matplotlib.use("TkAgg")
import matplotlib.pyplot as plt  # noqa: E402

from core.analyzer import (  # noqa: E402
    split_sentences,
    sentiment,
    detect_language,
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
_DARK_BG = "#1c1c1e"
_DARK_AXES_BG = "#2c2c2e"
_DARK_TEXT = "#f5f5f7"
_DARK_GRID = "#38383a"


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
    bar_color = "#0A84FF" if dark_mode else "#007AFF"
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


# ── 依存关系配色（按大类区分，视觉辨识度高）──
_DEP_COLORS = {
    # 主语 / 从句主语
    "nsubj": "#2563eb", "csubj": "#2563eb",
    "csubjpass": "#2563eb",
    # 宾语
    "dobj": "#16a34a", "obj": "#16a34a", "iobj": "#0d9488",
    "pobj": "#0d9488",
    # 修饰语
    "amod": "#ea580c", "advmod": "#ea580c", "nummod": "#ea580c",
    "nmod": "#db2777", "appos": "#db2777",
    # 限定 / 格
    "det": "#9333ea", "case": "#9333ea", "predet": "#9333ea",
    # 助动词 / 系词
    "aux": "#0891b2", "auxpass": "#0891b2", "cop": "#0891b2",
    # 复合 / 专名
    "compound": "#6366f1", "compound:nn": "#6366f1", "name": "#6366f1",
    # 从句
    "acl": "#d946ef", "relcl": "#d946ef", "ccomp": "#d946ef",
    "xcomp": "#f59e0b", "advcl": "#f59e0b",
    # 标点 / 并列 / 标记
    "punct": "#9ca3af", "cc": "#9ca3af", "conj": "#9ca3af",
    "mark": "#9ca3af", "prep": "#9ca3af",
    # 其他
    "neg": "#ef4444", "expl": "#84cc16", "discourse": "#9ca3af",
    "dep": "#6b7280", "parataxis": "#9ca3af", "intj": "#e11d48",
    "dative": "#0d9488", "npadvmod": "#ea580c", "poss": "#9333ea",
    "nmod:assmod": "#db2777", "nsubjpass": "#2563eb",
    "vocative": "#e11d48", "meta": "#9ca3af",
}
_DEP_COLOR_FALLBACK = "#6b7280"


def _resolve_head_local(dep: dict, sent: List[dict]) -> Optional[int]:
    """在句内定位 head token 的局部下标。"""
    h_global = dep.get("head_i")
    if h_global is not None:
        for j, d2 in enumerate(sent):
            if d2.get("token_i") == h_global:
                return j
    # 降级：文本匹配
    h_text = dep.get("head_text", "")
    candidates = [j for j, d2 in enumerate(sent)
                  if d2.get("text") == h_text and j != dep.get("token_i")]
    if candidates:
        return min(candidates, key=lambda j: abs(j - (dep.get("sent_i", len(sent) // 2))))
    return None


def _build_dep_edges(sent: List[dict]) -> tuple:
    """从一句的依存数据构建边列表并定位 ROOT。

    Returns:
        (root_i, edges, roots) —— edges 为 [{child, head, label}]，下标均为句内局部下标；
        roots 为所有 ROOT 节点的下标列表（spaCy 偶尔会产生多个 ROOT）。
    """
    root_i: Optional[int] = None
    roots: List[int] = []
    edges: List[dict] = []

    for i, d in enumerate(sent):
        if d.get("dep") == "ROOT":
            if root_i is None:
                root_i = i
            roots.append(i)
        else:
            h_local = _resolve_head_local(d, sent)
            if h_local is not None and h_local != i:
                edges.append({"child": i, "head": h_local, "label": d.get("dep", "")})

    if root_i is None and len(sent) > 0:
        root_i = 0
        roots = [0]
    return root_i, edges, roots


# --------------------------------------------------------------------------- #
# 思维导图风格的依存句法树
# --------------------------------------------------------------------------- #


def _build_dep_tree(sent: List[dict]) -> Optional[dict]:
    """从一句的依存数据构建树结构。

    容错处理：
    - head 自指（child == head）但 dep != ROOT：跳过该边
    - 环形引用：在深度计算时检测已访问节点，避免无限递归
    - 多个 ROOT：spaCy 偶尔会把一句内部切成多个 sents，产生多个 ROOT；
      此时引入虚拟根节点（idx=-1），把所有 ROOT 作为其子节点，
      保证所有 token 都能被布局到，避免 KeyError。

    Returns
    -------
    dict or None
        ``{"nodes": [...], "root": root_i}``，每个 node 含
        ``idx / token / children / parent / dep_label / depth``。
        若存在多 ROOT，``root`` 指向虚拟根（idx=-1）。
    """
    root_i, edges, roots = _build_dep_edges(sent)
    if root_i is None:
        return None

    # 虚拟根节点（仅当多 ROOT 时使用）
    use_virtual = len(roots) > 1
    virtual_node = {
        "idx": -1,
        "token": {"text": "", "pos": ""},
        "children": list(roots),
        "parent": None,
        "dep_label": "",
        "depth": 0,
    }

    nodes = [
        {
            "idx": i,
            "token": d,
            "children": [],
            "parent": None,
            "dep_label": "",
            "depth": 0,
        }
        for i, d in enumerate(sent)
    ]
    for e in edges:
        if e["child"] == e["head"]:
            continue
        nodes[e["child"]]["parent"] = e["head"]
        nodes[e["child"]]["dep_label"] = e["label"]
        nodes[e["head"]]["children"].append(e["child"])

    # 多 ROOT：把每个 ROOT 的 parent 设为虚拟根
    if use_virtual:
        for r in roots:
            nodes[r]["parent"] = -1
        all_nodes = [virtual_node] + nodes
        root_idx = -1  # 虚拟根在 all_nodes 中的索引（用 -1 标识）
    else:
        all_nodes = nodes
        root_idx = root_i

    # 计算深度（迭代避免栈溢出，visited 防环）
    # 虚拟根 depth=0，真实 ROOT depth=1，逐层 +1
    visited: set = set()
    start_depth = 1 if use_virtual else 0
    start_idx = root_i if not use_virtual else None
    if use_virtual:
        virtual_node["depth"] = 0
        stack = [(r, start_depth) for r in roots]
    else:
        stack = [(root_i, start_depth)]
    while stack:
        idx, d = stack.pop()
        if idx in visited:
            continue
        visited.add(idx)
        nodes[idx]["depth"] = d
        for c in nodes[idx]["children"]:
            if c not in visited:
                stack.append((c, d + 1))

    # 标记未访问的孤立节点（depth=0 但不是 ROOT）
    for n in nodes:
        if n["idx"] not in visited and n["idx"] not in roots:
            # 孤立节点：作为虚拟根的直接子节点
            n["depth"] = 1
            n["parent"] = -1
            virtual_node["children"].append(n["idx"])
            if not use_virtual:
                use_virtual = True
                all_nodes = [virtual_node] + nodes
                root_idx = -1

    return {"nodes": all_nodes, "root": root_idx, "virtual": use_virtual}


def _layout_tree_vertical(tree: dict,
                         dy: float = 1.0,
                         y_offset: float = 0.0) -> dict:
    """纵向布局（HanLP 竖版）：所有词在同一列，按 idx 竖直排列、右端对齐。

    - 每个词的 y = (n - 1 - idx) × dy + y_offset（idx 小的在上=大 y）
    - 所有词的 x 相同（右端对齐线，``x_right``）
    - 父子节点之间不通过 x 区分层级，而是通过**曲线向左凸出的幅度**
      表现依存关系（跨度越大，弧越深）。

    注意：``tree["nodes"]`` 可能含虚拟根（idx=-1），虚拟根不参与布局。
    """
    nodes_list = tree["nodes"]

    # 收集真实节点（idx >= 0），按 idx 升序
    real_nodes = sorted([n for n in nodes_list if n["idx"] >= 0],
                        key=lambda n: n["idx"])
    n = len(real_nodes)
    if n == 0:
        return {}

    positions: dict[int, tuple[float, float]] = {}
    x_right = 0.0  # 右端对齐线（x=0）
    for node in real_nodes:
        idx = node["idx"]
        # idx 小的在上（大 y），idx 大的在下（小 y）
        y = (n - 1 - idx) * dy + y_offset
        positions[idx] = (x_right, y)

    return positions


# 节点统一尺寸常量（所有词框大小一致，保持整齐）
_NODE_W = 2.0   # 节点宽度
_NODE_H = 0.8   # 节点高度
# 弧/箭头与节点框之间的视觉间隙（防止曲线与框"混在一起"）
_ARC_GAP = 0.15


def _draw_tree_connections(ax, tree: dict, pos: dict,
                           dark_mode: bool, bg: str) -> None:
    """绘制父子节点之间的向左凸出半圆弧，并标注依存关系。

    布局特点（HanLP 竖版）：
    - 所有词在同一列，节点右边缘对齐到 x=0，向左延伸到 x=-_NODE_W
    - 节点框左边缘（可见）位于 x = -_NODE_W
    - 曲线从 head 节点框左边缘**外侧** (x = -_NODE_W - _ARC_GAP) 出发，
      到 child 节点框左边缘**外侧**，弧向左凸出，绝不穿入节点框
    - 箭头在 child 端：从弧末端向右指向 child 节点框左边缘外侧（留小间隙）
    - 关系标签放在弧的最左端（凸出处）
    """
    import numpy as np

    # 弧起止点的 x 坐标（节点左边缘外侧，留出 _ARC_GAP 间隙）
    x_arc = -_NODE_W - _ARC_GAP
    # 箭头尖的 x 坐标（节点左边缘外侧，留出更小间隙以指示方向）
    x_arrow_tip = -_NODE_W - _ARC_GAP * 0.4

    nodes = tree["nodes"]
    for node in nodes:
        if node["idx"] == -1:
            continue
        if node["parent"] is None or node["parent"] == -1:
            continue
        if node["parent"] not in pos or node["idx"] not in pos:
            continue

        _, y_h = pos[node["parent"]]
        _, y_c = pos[node["idx"]]
        label = node["dep_label"]
        color = _DEP_COLORS.get(label, _DEP_COLOR_FALLBACK)

        # 向左凸出的半圆弧
        # 参数化 t ∈ [0, 1]：
        #   y(t) = y_h + (y_c - y_h) * t   （从 head 到 child 线性过渡）
        #   x(t) = x_arc - r * sin(π * t)  （t=0/1 时 x=x_arc，t=0.5 时 x=x_arc-r）
        # 弧深 r = 跨度的一半 = |y_h - y_c| / 2
        r = abs(y_h - y_c) / 2.0
        if r < 1e-3:
            continue  # head == child，跳过

        y_mid = (y_h + y_c) / 2.0
        t_param = np.linspace(0, 1, 48)
        xs = x_arc - r * np.sin(np.pi * t_param)
        ys = y_h + (y_c - y_h) * t_param

        ax.plot(xs, ys, color=color, lw=1.5, alpha=0.75, zorder=1,
                solid_capstyle="round")

        # 箭头在 child 端：从弧末端附近向右指向 child 节点框外侧（留小间隙）
        ax.annotate("",
                    xy=(x_arrow_tip, y_c),                   # 箭头尖：节点框外侧
                    xytext=(x_arc - min(r * 0.3, 0.4), y_c),  # 箭头尾：弧末端附近
                    arrowprops=dict(arrowstyle="-|>,head_width=0.25,head_length=0.2",
                                    lw=1.5, color=color),
                    zorder=3)

        # 关系标签：放在弧的最左端（凸出处）
        x_leftmost = x_arc - r
        ax.text(x_leftmost - 0.15, y_mid, label,
                ha="right", va="center",
                fontsize=7, color=color, style="italic", zorder=4,
                bbox=dict(boxstyle="round,pad=0.15", fc=bg, ec="none", alpha=0.9))


def _draw_tree_nodes(ax, tree: dict, pos: dict,
                     dark_mode: bool, colors: dict) -> None:
    """绘制节点（统一尺寸的圆角矩形 + 词文本 + 词性标签），右端对齐。

    布局：
    - 所有节点**统一尺寸**（_NODE_W × _NODE_H），右边对齐到 x=0，向左延伸到 x=-_NODE_W
    - 节点框**可见区域与边界矩形一致**（boxstyle pad=0），避免 pad 导致可见框
      向外扩展、与曲线/箭头视觉上"混在一起"
    - 词文本在框内**居中**显示
    - 词性标签放在节点的右侧（x > 0 区域），保持词列干净
    - 跳过虚拟根节点（idx=-1）。ROOT 节点判定：parent is None 或 parent == -1。
    """
    from matplotlib.patches import FancyBboxPatch

    nodes = tree["nodes"]
    for node in nodes:
        if node["idx"] == -1:
            continue
        if node["idx"] not in pos:
            continue
        _, y = pos[node["idx"]]  # x = 0（右端对齐线）
        text = node["token"].get("text", "")
        pos_tag = node["token"].get("pos", "")
        is_root = node["parent"] is None or node["parent"] == -1

        # 统一尺寸的圆角矩形节点：右边对齐到 x=0，向左延伸到 x=-_NODE_W
        # 注意：boxstyle 的 pad=0，使可见框与边界矩形完全一致；
        # 否则 pad 会让可见框向外扩展，导致曲线/箭头看起来"穿入"框内。
        rect = FancyBboxPatch(
            (-_NODE_W, y - _NODE_H / 2), _NODE_W, _NODE_H,
            boxstyle="round,pad=0,rounding_size=0.18",
            fc=colors["root_bg"] if is_root else colors["node_bg"],
            ec=colors["root_ec"] if is_root else colors["node_ec"],
            lw=1.8 if is_root else 1.0,
            zorder=2,
        )
        ax.add_patch(rect)

        # 词文本：在框内居中（x = -_NODE_W / 2）
        ax.text(-_NODE_W / 2, y, text,
                ha="center", va="center",
                fontsize=10.5 if is_root else 9.5,
                fontweight="bold",
                color=colors["root_text"] if is_root else colors["text"],
                zorder=3)

        # 词性标签：放在节点的右侧（x > 0）
        if pos_tag:
            ax.text(0.3, y, pos_tag,
                    ha="left", va="center",
                    fontsize=7,
                    color=colors["root_text"] if is_root else colors["secondary"],
                    style="italic", zorder=3)


def _enable_pan_zoom(fig, ax) -> None:
    """为 figure 启用拖拽平移和滚轮缩放（双击重置视图）。

    交互说明：
    - 鼠标左键拖拽：平移视图
    - 滚轮：以鼠标位置为中心缩放（向上放大、向下缩小）
    - 双击：重置到初始视图
    """
    init_xlim = ax.get_xlim()
    init_ylim = ax.get_ylim()
    state = {"pressed": False, "x": 0.0, "y": 0.0}

    def _on_press(event):
        if event.inaxes is not ax:
            return
        if event.dblclick:
            # 双击重置视图
            ax.set_xlim(init_xlim)
            ax.set_ylim(init_ylim)
            fig.canvas.draw_idle()
            return
        state["pressed"] = True
        state["x"] = event.xdata if event.xdata is not None else 0.0
        state["y"] = event.ydata if event.ydata is not None else 0.0

    def _on_motion(event):
        if not state["pressed"] or event.inaxes is not ax:
            return
        if event.xdata is None or event.ydata is None:
            return
        dx = event.xdata - state["x"]
        dy = event.ydata - state["y"]
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        ax.set_xlim(xlim[0] - dx, xlim[1] - dx)
        ax.set_ylim(ylim[0] - dy, ylim[1] - dy)
        state["x"] = event.xdata
        state["y"] = event.ydata
        fig.canvas.draw_idle()

    def _on_release(_event):
        state["pressed"] = False

    def _on_scroll(event):
        if event.inaxes is not ax:
            return
        # 以鼠标位置为中心缩放
        scale = 0.8 if event.button == "up" else 1.25
        cx = event.xdata
        cy = event.ydata
        if cx is None or cy is None:
            return
        xlim = ax.get_xlim()
        ylim = ax.get_ylim()
        ax.set_xlim(cx - (cx - xlim[0]) * scale,
                    cx + (xlim[1] - cx) * scale)
        ax.set_ylim(cy - (cy - ylim[0]) * scale,
                    cy + (ylim[1] - cy) * scale)
        fig.canvas.draw_idle()

    fig.canvas.mpl_connect("button_press_event", _on_press)
    fig.canvas.mpl_connect("motion_notify_event", _on_motion)
    fig.canvas.mpl_connect("button_release_event", _on_release)
    fig.canvas.mpl_connect("scroll_event", _on_scroll)


def make_dependency_graph(deps, title: str = "依存句法树",
                          dark_mode: bool = False,
                          sentence_index: Optional[int] = None) -> "plt.Figure":
    """绘制 Xmind 风格的横向树形依存句法图（支持拖拽与缩放）。

    布局要点：
    1. ROOT 词在最左侧，依存子节点逐层向右展开。
    2. 父子节点用平滑贝塞尔曲线连接，曲线颜色按依存关系分类。
    3. 每个节点为圆角矩形，显示词文本与词性；ROOT 节点用蓝色高亮。
    4. 支持鼠标交互：左键拖拽平移、滚轮缩放、双击重置视图。

    Parameters
    ----------
    deps : list[dict] or spacy.tokens.Doc or spacy.tokens.Span
        支持 :func:`core.analyzer.dependencies` 的输出或 spaCy 对象。
    title : str
    dark_mode : bool
    sentence_index : int or None
        若为 None，绘制全部句子；若为 int，仅绘制指定句子。

    Returns
    -------
    matplotlib.figure.Figure
    """
    # ── 归一化输入 ──
    if not isinstance(deps, list):
        deps = _deps_from_spacy(deps)
    if not deps:
        return _fallback_fig(title, "无依存数据（需安装 spaCy 模型）。", dark_mode)

    # ── 按 sent_id 分组 ──
    sentences: List[List[dict]] = []
    has_sent = any("sent_id" in d for d in deps)
    if has_sent:
        cur_sid, cur = None, []
        for d in deps:
            sid = d.get("sent_id", 0)
            if sid != cur_sid:
                if cur:
                    sentences.append(cur)
                cur, cur_sid = [d], sid
            else:
                cur.append(d)
        if cur:
            sentences.append(cur)
    else:
        sentences = [list(deps)]
    sentences = [s for s in sentences if s]

    # ── 单句过滤 ──
    if sentence_index is not None:
        if 0 <= sentence_index < len(sentences):
            sentences = [sentences[sentence_index]]
        else:
            return _fallback_fig(title, f"句子索引 {sentence_index} 超出范围。", dark_mode)

    # ── 构建每句的树 ──
    sent_trees: List[dict] = []
    for sent in sentences:
        tree = _build_dep_tree(sent)
        if tree is not None:
            sent_trees.append(tree)
    if not sent_trees:
        return _fallback_fig(title, "无法构建依存关系。", dark_mode)

    # ── 主题色 ──
    tc = _DARK_TEXT if dark_mode else "#1d1d1f"
    mc = _DARK_GRID if dark_mode else "#8e8e93"
    bg = _DARK_BG if dark_mode else "#ffffff"
    axes_bg = _DARK_AXES_BG if dark_mode else "#fafbfc"
    root_c = "#0A84FF" if dark_mode else "#007AFF"
    colors = {
        "text": tc,
        "secondary": mc,
        "root_text": root_c,
        "root_bg": "#1c3150" if dark_mode else "#e8f0ff",
        "root_ec": "#7b8cff" if dark_mode else "#4C78A8",
        "node_bg": "#2c2c3a" if dark_mode else "#ffffff",
        "node_ec": "#48484a" if dark_mode else "#d0d5dd",
    }

    # ── 纵向布局（HanLP 竖版，多句垂直堆叠，第 1 句在最上方）──
    # dy 包含节点高 _NODE_H 与词间空白；dy=1.7 时空白约 0.9，
    # 按当前 figure 比例约合 5mm 物理间距，避免词框过近
    dy = 1.7
    sent_gap_v = 2.0   # 句子间垂直间隔

    # 先对每句单独布局（y_offset=0），获取 y 跨度，用于计算整体排版
    sent_layouts_tmp: List[tuple] = []  # [(pos, y_min, y_max, height)]
    for tree in sent_trees:
        pos = _layout_tree_vertical(tree, dy=dy, y_offset=0.0)
        if pos:
            ys = [p[1] for p in pos.values()]
            y_min_i, y_max_i = min(ys), max(ys)
        else:
            y_min_i = y_max_i = 0.0
        sent_layouts_tmp.append((pos, y_min_i, y_max_i, y_max_i - y_min_i))

    # 计算总高度：所有句高度之和 + 句间间隔
    n_sents_actual = len(sent_trees)
    total_h = (sum(item[3] for item in sent_layouts_tmp)
               + sent_gap_v * (n_sents_actual - 1) if n_sents_actual > 0 else 0.0)

    # 反向分配 y_offset：第 0 句 y_offset 最大（最上方），逐句递减
    all_positions: List[dict] = []
    cursor = total_h  # 从顶部开始递减
    for i, tree in enumerate(sent_trees):
        height_i = sent_layouts_tmp[i][3]
        y_offset_i = cursor - height_i  # 该句底部位置
        pos = _layout_tree_vertical(tree, dy=dy, y_offset=y_offset_i)
        all_positions.append(pos)
        cursor = y_offset_i - sent_gap_v  # 下一句底部位置

    # ── 计算图尺寸（考虑弧向左延伸的深度）──
    # x 方向：所有词在 x=0，弧向左延伸，弧深 = 最大跨度/2
    # 需要计算每句的最大弧深
    max_arc_depth = 0.0
    for tree in sent_trees:
        nodes_map = {n["idx"]: n for n in tree["nodes"] if n["idx"] >= 0}
        for node in nodes_map.values():
            if node["parent"] is None or node["parent"] == -1:
                continue
            if node["parent"] not in nodes_map:
                continue
            # 跨度 = |idx_child - idx_parent|
            span = abs(node["idx"] - node["parent"])
            max_arc_depth = max(max_arc_depth, span / 2.0)

    # x 范围：[−max_arc_depth − 节点宽 − _ARC_GAP − 标签宽, +词性标签宽]
    label_w = 2.0     # 词性标签宽度
    x_min = -max_arc_depth - _NODE_W - _ARC_GAP - 1.5  # 左侧留白给标签
    x_max = label_w + 0.5

    y_min = min((p[1] for pos in all_positions for p in pos.values()), default=0.0)
    y_max = max((p[1] for pos in all_positions for p in pos.values()), default=0.0)
    y_range = y_max - y_min
    x_range = x_max - x_min

    fig_w = max(8, min(x_range * 0.45 + 2.0, 18))
    fig_h = max(6, min(y_range * 0.42 + 2.5, 24))

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    # ── 绘制每棵树 ──
    for i, tree in enumerate(sent_trees):
        pos = all_positions[i]
        _draw_tree_connections(ax, tree, pos, dark_mode, bg)
        _draw_tree_nodes(ax, tree, pos, dark_mode, colors)
        # 句子标题（右上角，靠近 ROOT 词）
        if len(sent_trees) > 1:
            # 找该句的 ROOT 节点位置
            root_idx = tree["root"]
            if root_idx >= 0 and root_idx in pos:
                root_y = pos[root_idx][1]
                ax.text(x_max - 0.1, root_y, f"S{i + 1}",
                        ha="right", va="center",
                        fontsize=12, fontweight="bold", color=root_c, style="italic",
                        bbox=dict(boxstyle="round,pad=0.2", fc=bg, ec=root_c, alpha=0.9, lw=0.8))

    # ── 视图设置 ──
    pad_x = 0.5
    pad_y = dy * 0.8
    ax.set_xlim(x_min - pad_x, x_max + pad_x)
    ax.set_ylim(y_min - pad_y, y_max + pad_y)
    ax.axis("off")
    ax.set_title(title, color=tc, fontsize=14, fontweight="bold", pad=12)

    if dark_mode:
        fig.patch.set_facecolor(_DARK_BG)
        ax.set_facecolor(_DARK_AXES_BG)
    else:
        fig.patch.set_facecolor(bg)
        ax.set_facecolor(axes_bg)

    # ── 交互提示（标题下方）──
    ax.text(0.01, 0.01, "拖拽平移 · 滚轮缩放 · 双击重置",
            transform=ax.transAxes, ha="left", va="bottom",
            fontsize=8, color=mc, alpha=0.7, style="italic")

    # ── 启用交互 ──
    _enable_pan_zoom(fig, ax)

    fig.tight_layout(pad=0.8)
    return fig


def _deps_from_spacy(doc) -> List[dict]:
    """把 spaCy Doc / Span 转成 :func:`dependencies` 兼容的 dict 列表。"""
    deps: List[dict] = []
    try:
        sents = list(doc.sents)
    except (AttributeError, TypeError):
        sents = [doc]
    for sid, sent in enumerate(sents):
        for t in sent:
            if t.is_space:
                continue
            deps.append({
                "text": t.text,
                "pos": t.pos_,
                "dep": t.dep_,
                "head_text": t.head.text,
                "head_pos": t.head.pos_,
                "head_i": t.head.i,
                "token_i": t.i,
                "sent_id": sid,
                "sent_i": t.i - sent.start if hasattr(sent, "start") else t.i,
            })
    return deps


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
        colors = ["#30d158" if v > 0.15 else "#ff453a" if v < -0.15 else "#98989d" for v in scores]
    else:
        colors = ["#34c759" if v > 0.15 else "#ff3b30" if v < -0.15 else "#8e8e93" for v in scores]

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
    labels: List[str] = ["A vs 嫌疑作者 B"]
    means: List[float] = [sim_b.mean_similarity]
    stds: List[float] = [sim_b.std_similarity]
    colors: List[str] = []

    accent = "#0A84FF" if dark_mode else "#007AFF"
    muted_gray = "#98989d" if dark_mode else "#8e8e93"
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
