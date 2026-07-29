"""统一的视觉样式：高 DPI 感知 + 双主题（浅色/深色）+ 现代化 ttk 主题。

必须在创建 ``Tk`` 之前调用 :func:`enable_dpi_awareness`，在创建之后调用
:func:`apply_style`。
"""

from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from tkinter import ttk
from dataclasses import dataclass
from typing import Callable, List


# --------------------------------------------------------------------------- #
# 配色数据类
# --------------------------------------------------------------------------- #

@dataclass
class ThemeColors:
    """一组完整的 UI 配色。"""
    name: str
    BG: str            # 窗口底色
    CARD: str          # 卡片背景
    ACCENT: str        # 主色
    ACCENT_HOVER: str  # 主色悬停
    ACCENT_SOFT: str   # 主色浅底
    TEXT: str          # 主文字
    MUTED: str         # 次要文字
    BORDER: str        # 边框
    SUCCESS: str       # 成功绿
    DANGER: str        # 危险红
    ROW_ALT: str       # 交替行背景
    SELECT_BG: str     # 选中背景
    MENU_BG: str       # 菜单背景
    MENU_FG: str       # 菜单文字
    INPUT_BG: str      # 输入框背景
    INPUT_FG: str      # 输入框文字
    SCROLL_BG: str     # 滚动条底色
    SCROLL_HOVER: str  # 滚动条悬停
    CHART_BG: str      # 图表背景
    CHART_TEXT: str    # 图表文字
    BUTTON_BG: str     # 普通按钮底色
    BUTTON_HOVER: str  # 普通按钮悬停


# --------------------------------------------------------------------------- #
# 浅色主题
# --------------------------------------------------------------------------- #

LIGHT_THEME = ThemeColors(
    name="light",
    BG="#f5f5f7",           # 系统灰
    CARD="#ffffff",
    ACCENT="#0071e3",        # 主色蓝
    ACCENT_HOVER="#0060c7",
    ACCENT_SOFT="#e8f2ff",
    TEXT="#1d1d1f",          # 主要标签色
    MUTED="#86868b",         # 次要标签色
    BORDER="#d2d2d7",        # 分隔线色
    SUCCESS="#30b158",       # 成功绿
    DANGER="#eb4d3e",        # 危险红
    ROW_ALT="#f5f5f7",
    SELECT_BG="#cce4ff",
    MENU_BG="#ffffff",
    MENU_FG="#1d1d1f",
    INPUT_BG="#ffffff",
    INPUT_FG="#1d1d1f",
    SCROLL_BG="#f0f0f3",
    SCROLL_HOVER="#d0d0d6",
    CHART_BG="#ffffff",
    CHART_TEXT="#1d1d1f",
    BUTTON_BG="#f0f0f3",
    BUTTON_HOVER="#e0e0e5",
)


# --------------------------------------------------------------------------- #
# 深色主题
# --------------------------------------------------------------------------- #

DARK_THEME = ThemeColors(
    name="dark",
    BG="#1c1c1e",           # 深色系统背景
    CARD="#2c2c2e",         # 深色卡片
    ACCENT="#0a84ff",        # 深色主色蓝
    ACCENT_HOVER="#409cff",
    ACCENT_SOFT="#1c3150",
    TEXT="#f5f5f7",         # 深色主要标签
    MUTED="#98989d",         # 深色次要标签
    BORDER="#3a3a3c",        # 深色分隔线
    SUCCESS="#30d158",       # 深色成功绿
    DANGER="#ff453a",        # 深色危险红
    ROW_ALT="#232325",
    SELECT_BG="#3a4f6b",
    MENU_BG="#2c2c2e",
    MENU_FG="#f5f5f7",
    INPUT_BG="#1c1c1e",
    INPUT_FG="#f5f5f7",
    SCROLL_BG="#2c2c2e",
    SCROLL_HOVER="#48484a",
    CHART_BG="#1c1c1e",
    CHART_TEXT="#f5f5f7",
    BUTTON_BG="#3a3a3c",
    BUTTON_HOVER="#48484a",
)


# --------------------------------------------------------------------------- #
# 字体 — 排版层级
# --------------------------------------------------------------------------- #

FONT = "Microsoft YaHei UI"          # 系统 UI 字体
FONT_MONO = "Consolas"              # 等宽字体

# 文本样式层级（适配桌面端 13pt 基准）
# 正文默认 13pt，与 8pt 网格对齐
FONT_SCALE = {
    "largeTitle":   20,   # 屏幕标题
    "title":        17,   # 区域标题
    "title2":       15,   # 子区域标题
    "title3":       13,   # 分组标题
    "headline":     11,   # 行标题 (Semibold)
    "body":         10,   # 正文
    "callout":      10,   # 次要内容 (同 body，区分语义)
    "footnote":      9,   # 辅助文字
    "caption":       8,   # 标签 / 小标签
}

# 字重映射 — 避免 Ultralight/Thin/Light
FONT_WEIGHTS = {
    "regular":      "normal",
    "medium":       "normal",    # tkinter 仅支持 normal/bold；用大小区分
    "semibold":     "bold",
    "bold":         "bold",
}


# --------------------------------------------------------------------------- #
# 系统主题检测
# --------------------------------------------------------------------------- #

def detect_system_dark_mode() -> bool:
    """读取 Windows 注册表，判断当前系统是否使用深色模式。非 Windows 返回 False。"""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return value == 0  # 0 = dark, 1 = light
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# 主题管理
# --------------------------------------------------------------------------- #

_current_theme: ThemeColors = LIGHT_THEME
_callbacks: List[Callable[[ThemeColors], None]] = []


def get_theme() -> ThemeColors:
    """返回当前激活的主题。"""
    return _current_theme


def register_theme_callback(fn: Callable[[ThemeColors], None]) -> None:
    """注册主题变更回调，切换主题时自动调用。用于更新非 ttk 组件颜色。"""
    if fn not in _callbacks:
        _callbacks.append(fn)


def unregister_theme_callback(fn: Callable[[ThemeColors], None]) -> None:
    """移除之前注册的回调。"""
    if fn in _callbacks:
        _callbacks.remove(fn)


def _fire_theme_callbacks() -> None:
    for fn in _callbacks:
        try:
            fn(_current_theme)
        except Exception:
            pass


def toggle_theme(root: tk.Tk) -> str:
    """切换浅色/深色主题，返回新主题名（'light' 或 'dark'）。"""
    global _current_theme
    _current_theme = DARK_THEME if _current_theme is LIGHT_THEME else LIGHT_THEME
    apply_style(root)
    _fire_theme_callbacks()
    return _current_theme.name


def set_theme(root: tk.Tk, name: str) -> None:
    """直接设置主题。"""
    global _current_theme
    if name == "dark":
        _current_theme = DARK_THEME
    else:
        _current_theme = LIGHT_THEME
    apply_style(root)
    _fire_theme_callbacks()


# --------------------------------------------------------------------------- #
# 模块级快捷方式（向后兼容：s.BG / s.TEXT 等实时反映当前主题）
# --------------------------------------------------------------------------- #

# 预计算合法颜色属性名集合
_THEME_ATTRS = {f.name for f in ThemeColors.__dataclass_fields__.values()}


def __getattr__(name):
    """模块级属性代理：s.BG / s.TEXT 等自动返回当前主题颜色。"""
    if name in _THEME_ATTRS:
        return getattr(_current_theme, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# --------------------------------------------------------------------------- #
# 高 DPI
# --------------------------------------------------------------------------- #


def enable_dpi_awareness() -> None:
    """让 Windows 以高分辨率渲染，避免界面模糊。必须在 Tk() 之前调用。"""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# 响应式布局基础设施
# --------------------------------------------------------------------------- #

_screen_size: "tuple[int, int] | None" = None


def get_screen_size() -> "tuple[int, int]":
    """返回主显示器宽高 (w, h)，缓存结果。"""
    global _screen_size
    if _screen_size is not None:
        return _screen_size
    try:
        # 优先用 tkinter 获取（需要 root 已创建，fallback 用 ctypes）
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        w = root.winfo_screenwidth()
        h = root.winfo_screenheight()
        root.destroy()
        _screen_size = (w, h)
    except Exception:
        # 最终 fallback: 假设 1080p
        _screen_size = (1920, 1080)
    return _screen_size


def get_scale_factor() -> float:
    """根据屏幕高度返回缩放因子。

    >= 1440px 高: 1.00  (2K/4K 显示器)
    >= 1080px 高: 0.92  (1080p)
    >=  900px 高: 0.85  (900p)
    >=  768px 高: 0.78  (1366×768 笔记本)
    >=  720px 高: 0.72  (720p)
    """
    _, h = get_screen_size()
    if h >= 1440:
        return 1.0
    if h >= 1080:
        return 0.92
    if h >= 900:
        return 0.85
    if h >= 768:
        return 0.78
    return 0.72


def get_responsive_window_size() -> "tuple[int, int]":
    """返回自适应窗口尺寸 (w, h)。

    宽度: min(1400, 屏幕宽×0.88)
    高度: min(920, 屏幕高×0.90)
    但至少 1024×680。
    """
    sw, sh = get_screen_size()
    w = min(1400, int(sw * 0.88))
    h = min(920, int(sh * 0.90))
    w = max(w, 1024)
    h = max(h, 680)
    return (w, h)


def get_responsive_min_size() -> "tuple[int, int]":
    """返回自适应最小窗口尺寸。

    720p:  880×560
    768p:  920×580
    其他:  1024×640
    """
    _, sh = get_screen_size()
    if sh <= 720:
        return (860, 560)
    if sh <= 768:
        return (920, 600)
    return (1024, 640)


def is_compact_mode() -> bool:
    """屏幕高度 ≤ 768px 时启用紧凑模式。"""
    _, sh = get_screen_size()
    return sh <= 768


def get_responsive_font_scale() -> float:
    """字体缩放因子（紧凑模式下略微缩小）。"""
    return 0.92 if is_compact_mode() else 1.0


def responsive_padding(base: int) -> int:
    """根据屏幕缩放因子调整 padding 值。"""
    return max(4, int(base * get_scale_factor()))


def responsive_font_size(base: int) -> int:
    """根据屏幕缩放因子调整字号。"""
    return max(8, int(base * get_responsive_font_scale()))


# --------------------------------------------------------------------------- #
# 样式应用
# --------------------------------------------------------------------------- #


def apply_style(root: tk.Tk) -> None:
    """根据当前主题重新配置全部 ttk 样式与 tk 全局默认值。"""
    t = get_theme()
    style = ttk.Style(root)

    # 确保使用 clam 主题（最可定制）
    try:
        style.theme_use("clam")
    except Exception:
        pass

    # ── 响应式字号 ──
    _body_sz = responsive_font_size(FONT_SCALE["body"])           # 10 → 9 (compact)
    _headline_sz = responsive_font_size(FONT_SCALE["headline"])   # 11 → 10
    _title3_sz = responsive_font_size(FONT_SCALE["title3"])       # 13 → 12
    _title2_sz = responsive_font_size(FONT_SCALE["title2"])       # 15 → 14
    _title_sz = responsive_font_size(FONT_SCALE["title"])         # 17 → 15
    _footnote_sz = responsive_font_size(FONT_SCALE["footnote"])   # 9 → 8
    _caption_sz = responsive_font_size(FONT_SCALE["caption"])     # 8 → 7

    # ===================================================================== #
    # 全局默认 — 排版层级
    # ===================================================================== #
    style.configure(".", background=t.BG, foreground=t.TEXT,
                    font=(FONT, _body_sz),
                    troughcolor=t.BG, fieldbackground=t.INPUT_BG)

    style.configure("TFrame", background=t.BG)
    style.configure("TLabel", background=t.BG, foreground=t.TEXT,
                    font=(FONT, _body_sz))

    # 语义标签样式 — labelColor 体系
    style.configure("Muted.TLabel", background=t.BG, foreground=t.MUTED,
                    font=(FONT, _footnote_sz))
    style.configure("Title.TLabel", background=t.BG, foreground=t.TEXT,
                    font=(FONT, _title2_sz, "bold"))
    style.configure("Subtitle.TLabel", background=t.BG, foreground=t.MUTED,
                    font=(FONT, _footnote_sz))
    style.configure("Headline.TLabel", background=t.BG, foreground=t.TEXT,
                    font=(FONT, _headline_sz, "bold"))
    style.configure("Callout.TLabel", background=t.BG, foreground=t.TEXT,
                    font=(FONT, _body_sz))
    style.configure("Footnote.TLabel", background=t.BG, foreground=t.MUTED,
                    font=(FONT, _footnote_sz))
    style.configure("Caption.TLabel", background=t.BG, foreground=t.MUTED,
                    font=(FONT, _caption_sz))

    # ===================================================================== #
    # 卡片容器 — 柔和边框 + 充足内边距 + 8px 圆角
    # ===================================================================== #
    style.configure(
        "Card.TLabelframe",
        background=t.CARD,
        bordercolor=t.BORDER,
        relief="solid",
        borderwidth=1,
    )
    style.configure(
        "Card.TLabelframe.Label",
        background=t.CARD,
        foreground=t.TEXT,
        font=(FONT, _headline_sz, "bold"),
    )

    # 强调卡片（用于首次引导 / 重要区域）
    style.configure(
        "Emphasis.TLabelframe",
        background=t.ACCENT_SOFT,
        bordercolor=t.ACCENT,
        relief="solid",
        borderwidth=1,
    )
    style.configure(
        "Emphasis.TLabelframe.Label",
        background=t.ACCENT_SOFT,
        foreground=t.ACCENT,
        font=(FONT, _headline_sz, "bold"),
    )

    # ===================================================================== #
    # 按钮 — 层级：Accent (filled) > Secondary (borderless) > Tertiary (plain)
    # ===================================================================== #
    # 标准按钮 (Tertiary)
    style.configure(
        "TButton",
        font=(FONT, _body_sz),
        padding=(16, 8),
        background=t.BUTTON_BG,
        foreground=t.TEXT,
        borderwidth=0,
        relief="flat",
    )
    style.map(
        "TButton",
        background=[("active", t.BUTTON_HOVER), ("pressed", t.BUTTON_HOVER)],
        foreground=[("active", t.TEXT)],
    )

    # 主按钮 (Accent / Filled) — 仅一个页面一个
    style.configure(
        "Accent.TButton",
        font=(FONT, _body_sz, "bold"),
        padding=(20, 9),
        background=t.ACCENT,
        foreground="#ffffff",
        borderwidth=0,
        relief="flat",
    )
    style.map(
        "Accent.TButton",
        background=[("active", t.ACCENT_HOVER), ("pressed", t.ACCENT_HOVER)],
        foreground=[("active", "#ffffff"), ("disabled", "#a0a0c0")],
    )

    # 次要按钮 (Secondary / Borderless accent)
    style.configure(
        "Secondary.TButton",
        font=(FONT, _body_sz),
        padding=(16, 8),
        background=t.CARD,
        foreground=t.ACCENT,
        borderwidth=0,
        relief="flat",
    )
    style.map(
        "Secondary.TButton",
        background=[("active", t.ACCENT_SOFT), ("pressed", t.ACCENT_SOFT)],
        foreground=[("active", t.ACCENT)],
    )

    # 危险按钮
    style.configure(
        "Danger.TButton",
        font=(FONT, _body_sz),
        padding=(14, 7),
        background=t.ROW_ALT,
        foreground=t.DANGER,
        borderwidth=0,
        relief="flat",
    )
    style.map(
        "Danger.TButton",
        background=[("active", t.BORDER)],
        foreground=[("active", t.DANGER)],
    )

    # 注：主题切换按钮使用 tk.Button（见 main_window.py），不依赖 ttk 样式

    # ===================================================================== #
    # 输入控件 — 柔和边框 + 聚焦高亮
    # ===================================================================== #
    style.configure(
        "TEntry",
        fieldbackground=t.INPUT_BG,
        foreground=t.INPUT_FG,
        bordercolor=t.BORDER,
        lightcolor=t.BORDER,
        darkcolor=t.BORDER,
        relief="solid",
        borderwidth=1,
        padding=6,
        font=(FONT, _body_sz),
    )
    style.map(
        "TEntry",
        bordercolor=[("focus", t.ACCENT)],
        lightcolor=[("focus", t.ACCENT)],
        darkcolor=[("focus", t.ACCENT)],
    )

    style.configure(
        "TCombobox",
        fieldbackground=t.INPUT_BG,
        background=t.CARD,
        foreground=t.TEXT,
        bordercolor=t.BORDER,
        lightcolor=t.BORDER,
        darkcolor=t.BORDER,
        relief="solid",
        borderwidth=1,
        padding=6,
        arrowcolor=t.MUTED,
        font=(FONT, _body_sz),
    )
    style.map(
        "TCombobox",
        bordercolor=[("focus", t.ACCENT)],
        fieldbackground=[("readonly", t.INPUT_BG)],
    )
    # Combobox 下拉列表
    root.option_add("*TCombobox*Listbox.background", t.CARD)
    root.option_add("*TCombobox*Listbox.foreground", t.TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", t.ACCENT_SOFT)
    root.option_add("*TCombobox*Listbox.selectForeground", t.TEXT)
    root.option_add("*TCombobox*Listbox.font", (FONT, _body_sz))

    # ===================================================================== #
    # Notebook 标签页 — 分段控件风格
    # ===================================================================== #
    style.configure(
        "TNotebook",
        background=t.BG,
        borderwidth=0,
        tabmargins=(2, 6, 2, 0),
    )
    style.configure(
        "TNotebook.Tab",
        background=t.BG,
        foreground=t.MUTED,
        padding=(24, 11),
        font=(FONT, _body_sz),
        borderwidth=0,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", t.CARD)],
        foreground=[("selected", t.ACCENT)],
        expand=[("selected", (1, 1, 1, 0))],
    )

    # Notebook 内嵌子 Notebook（句法页）
    style.configure(
        "Sub.TNotebook",
        background=t.CARD,
        borderwidth=0,
        tabmargins=(2, 4, 2, 0),
    )
    style.configure(
        "Sub.TNotebook.Tab",
        background=t.CARD,
        foreground=t.MUTED,
        padding=(16, 7),
        font=(FONT, _footnote_sz),
        borderwidth=0,
    )
    style.map(
        "Sub.TNotebook.Tab",
        background=[("selected", t.BG)],
        foreground=[("selected", t.ACCENT)],
    )

    # ===================================================================== #
    # PanedWindow
    # ===================================================================== #
    style.configure("TPanedwindow", background=t.BG)
    style.configure("Sash", background=t.BORDER, borderwidth=0, sashthickness=4)

    # ===================================================================== #
    # 滚动条
    # ===================================================================== #
    style.configure(
        "Vertical.TScrollbar",
        background=t.SCROLL_BG,
        troughcolor=t.BG,
        bordercolor=t.BG,
        arrowcolor=t.MUTED,
        relief="flat",
        arrowsize=14,
    )
    style.map(
        "Vertical.TScrollbar",
        background=[("active", t.SCROLL_HOVER), ("pressed", t.SCROLL_HOVER)],
    )

    style.configure(
        "Horizontal.TScrollbar",
        background=t.SCROLL_BG,
        troughcolor=t.BG,
        bordercolor=t.BG,
        arrowcolor=t.MUTED,
        relief="flat",
        arrowsize=14,
    )
    style.map(
        "Horizontal.TScrollbar",
        background=[("active", t.SCROLL_HOVER), ("pressed", t.SCROLL_HOVER)],
    )

    # ===================================================================== #
    # Treeview（历史记录用）
    # ===================================================================== #
    style.configure(
        "Treeview",
        background=t.CARD,
        foreground=t.TEXT,
        fieldbackground=t.CARD,
        borderwidth=0,
        font=(FONT, _body_sz),
        rowheight=36,
    )
    style.configure(
        "Treeview.Heading",
        background=t.ROW_ALT,
        foreground=t.MUTED,
        font=(FONT, _footnote_sz, "bold"),
        borderwidth=0,
        padding=(10, 6),
    )
    style.map(
        "Treeview",
        background=[("selected", t.ACCENT_SOFT)],
        foreground=[("selected", t.TEXT)],
    )
    style.map(
        "Treeview.Heading",
        background=[("active", t.BORDER)],
    )

    # ===================================================================== #
    # 进度条
    # ===================================================================== #
    style.configure(
        "TProgressbar",
        background=t.ACCENT,
        troughcolor=t.BG,
        borderwidth=0,
        thickness=6,
    )

    # ===================================================================== #
    # Separator
    # ===================================================================== #
    style.configure(
        "TSeparator",
        background=t.BORDER,
    )

    # ===================================================================== #
    # 菜单（尽力而为 — tkinter 菜单支持有限）
    # ===================================================================== #
    root.option_add("*Menu.background", t.MENU_BG)
    root.option_add("*Menu.foreground", t.MENU_FG)
    root.option_add("*Menu.activeBackground", t.ACCENT_SOFT)
    root.option_add("*Menu.activeForeground", t.TEXT)
    root.option_add("*Menu.borderWidth", 0)
    root.option_add("*Menu.font", (FONT, _body_sz))

    # ===================================================================== #
    # Text / ScrolledText（通过 option_db 设置默认值）
    # ===================================================================== #
    root.option_add("*Text.background", t.INPUT_BG)
    root.option_add("*Text.foreground", t.INPUT_FG)
    root.option_add("*Text.font", (FONT_MONO, _body_sz))
    root.option_add("*Text.borderWidth", 0)
    root.option_add("*Text.highlightThickness", 1)
    root.option_add("*Text.highlightBackground", t.BORDER)
    root.option_add("*Text.highlightColor", t.ACCENT)
    root.option_add("*Text.selectBackground", t.SELECT_BG)
    root.option_add("*Text.selectForeground", t.TEXT)
    root.option_add("*Text.insertBackground", t.TEXT)
    root.option_add("*Text.padX", 10)
    root.option_add("*Text.padY", 8)

    # ===================================================================== #
    # 窗口背景
    # ===================================================================== #
    root.configure(bg=t.BG)
