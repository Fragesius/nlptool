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
    BG="#eef1f5",
    CARD="#ffffff",
    ACCENT="#2f6fed",
    ACCENT_HOVER="#1f57c8",
    ACCENT_SOFT="#e7efff",
    TEXT="#1f2733",
    MUTED="#6b7480",
    BORDER="#d8dce6",
    SUCCESS="#16a34a",
    DANGER="#dc2626",
    ROW_ALT="#f4f6fb",
    SELECT_BG="#d6e4ff",
    MENU_BG="#ffffff",
    MENU_FG="#1f2733",
    INPUT_BG="#ffffff",
    INPUT_FG="#1f2733",
    SCROLL_BG="#eef1f5",
    SCROLL_HOVER="#d0d5de",
    CHART_BG="#ffffff",
    CHART_TEXT="#1f2733",
    BUTTON_BG="#e6e9ef",
    BUTTON_HOVER="#d0d5de",
)


# --------------------------------------------------------------------------- #
# 深色主题
# --------------------------------------------------------------------------- #

DARK_THEME = ThemeColors(
    name="dark",
    BG="#141529",
    CARD="#1e2038",
    ACCENT="#7b8cff",
    ACCENT_HOVER="#99a5ff",
    ACCENT_SOFT="#1f2245",
    TEXT="#e2e4f0",
    MUTED="#8b8fa8",
    BORDER="#2d3050",
    SUCCESS="#4ade80",
    DANGER="#f87171",
    ROW_ALT="#191c30",
    SELECT_BG="#2a2f55",
    MENU_BG="#1e2038",
    MENU_FG="#e2e4f0",
    INPUT_BG="#1a1c2e",
    INPUT_FG="#e2e4f0",
    SCROLL_BG="#1e2038",
    SCROLL_HOVER="#3d4060",
    CHART_BG="#141529",
    CHART_TEXT="#e2e4f0",
    BUTTON_BG="#2a2d48",
    BUTTON_HOVER="#353858",
)


# --------------------------------------------------------------------------- #
# 字体
# --------------------------------------------------------------------------- #

FONT = "Microsoft YaHei UI"
FONT_MONO = "Consolas"


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

    # ===================================================================== #
    # 全局默认
    # ===================================================================== #
    style.configure(".", background=t.BG, foreground=t.TEXT, font=(FONT, 10),
                    troughcolor=t.BG, fieldbackground=t.INPUT_BG)

    style.configure("TFrame", background=t.BG)
    style.configure("TLabel", background=t.BG, foreground=t.TEXT, font=(FONT, 10))
    style.configure("Muted.TLabel", background=t.BG, foreground=t.MUTED, font=(FONT, 9))
    style.configure("Title.TLabel", background=t.BG, foreground=t.TEXT, font=(FONT, 15, "bold"))
    style.configure("Subtitle.TLabel", background=t.BG, foreground=t.MUTED, font=(FONT, 9))

    # ===================================================================== #
    # 卡片容器
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
        font=(FONT, 10, "bold"),
    )

    # ===================================================================== #
    # 按钮
    # ===================================================================== #
    style.configure(
        "TButton",
        font=(FONT, 10),
        padding=(14, 7),
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

    # 主按钮（强调色）
    style.configure(
        "Accent.TButton",
        font=(FONT, 10, "bold"),
        padding=(18, 8),
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

    # 危险按钮
    style.configure(
        "Danger.TButton",
        font=(FONT, 10),
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
    # 输入控件
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
    root.option_add("*TCombobox*Listbox.font", (FONT, 10))

    # ===================================================================== #
    # Notebook 标签页
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
        padding=(22, 10),
        font=(FONT, 10),
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
        font=(FONT, 9),
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
        font=(FONT, 10),
        rowheight=32,
    )
    style.configure(
        "Treeview.Heading",
        background=t.ROW_ALT,
        foreground=t.MUTED,
        font=(FONT, 9, "bold"),
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
    root.option_add("*Menu.font", (FONT, 10))

    # ===================================================================== #
    # Text / ScrolledText（通过 option_db 设置默认值）
    # ===================================================================== #
    root.option_add("*Text.background", t.INPUT_BG)
    root.option_add("*Text.foreground", t.INPUT_FG)
    root.option_add("*Text.font", (FONT_MONO, 10))
    root.option_add("*Text.borderWidth", 0)
    root.option_add("*Text.highlightThickness", 1)
    root.option_add("*Text.highlightBackground", t.BORDER)
    root.option_add("*Text.highlightColor", t.ACCENT)
    root.option_add("*Text.selectBackground", t.SELECT_BG)
    root.option_add("*Text.selectForeground", t.TEXT)
    root.option_add("*Text.insertBackground", t.TEXT)
    root.option_add("*Text.padX", 8)
    root.option_add("*Text.padY", 6)

    # ===================================================================== #
    # 窗口背景
    # ===================================================================== #
    root.configure(bg=t.BG)
