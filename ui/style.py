"""全局视觉样式：customtkinter 墨绿学术主题 + 语义色 + 响应式工具。

使用方式：
- 创建根窗口 **之前** 调用 :func:`enable_dpi_awareness` 与 :func:`init_appearance`
- 主题由 customtkinter 自动管理（跟随系统深/浅色），手动切换用
  :func:`set_appearance` / :func:`toggle_appearance`
- 配色统一走本模块常量（``[浅色, 深色]`` 双色元组，CTk 控件自动选用）
"""

from __future__ import annotations

import ctypes
import os
import sys

import customtkinter as ctk

# --------------------------------------------------------------------------- #
# 配色 — 墨绿学术风（[浅色模式, 深色模式]）
# --------------------------------------------------------------------------- #

ACCENT = ("#31584C", "#3D6B5A")        # 主强调色（墨绿）
ACCENT_HOVER = ("#25443B", "#4A7D6B")  # 主色悬停
ACCENT_SOFT = ("#E1ECE6", "#24382F")   # 主色浅底（标签/高亮）
SUCCESS = ("#2E7D46", "#4CAF70")       # 成功 / 显著
DANGER = ("#B3402F", "#E0685A")        # 危险 / 错误
MUTED = ("#6E7B76", "#9AA5A0")         # 次要文字 / 不显著
BORDER = ("#C9D2CE", "#3A4742")        # 边框
CARD = ("#FFFFFF", "#222A26")         # 卡片背景
BG = ("#F3F5F4", "#171C1A")            # 窗口底色
TEXT = ("#1E2422", "#E8ECEA")          # 主文字

# 次要按钮（非强调）配色
BUTTON_NEUTRAL = ("#E4E9E6", "#2C3531")
BUTTON_NEUTRAL_HOVER = ("#D3DCD7", "#3A4742")


def resolve(color) -> str:
    """把 ``[浅色, 深色]`` 双色解析为当前模式下的单色（供菜单/matplotlib 用）。"""
    if isinstance(color, (tuple, list)):
        return color[1] if is_dark() else color[0]
    return color


# --------------------------------------------------------------------------- #
# 字体 — 排版层级
# --------------------------------------------------------------------------- #

FONT = "Microsoft YaHei UI"           # 系统 UI 字体
FONT_MONO = "Consolas"                # 等宽字体（结果区）

FONT_SCALE = {
    "largeTitle":   22,   # 屏幕标题
    "title":        19,   # 区域标题
    "title2":       17,   # 子区域标题
    "title3":       15,   # 分组标题
    "headline":     13,   # 行标题
    "body":         12,   # 正文
    "callout":      11,   # 次要内容
    "footnote":     10,   # 辅助文字
    "caption":       9,   # 小标签
}


def font(key: str = "body", bold: bool = False, mono: bool = False) -> tuple:
    """构造 CTk 字体元组 ``(family, size[, weight])``。"""
    family = FONT_MONO if mono else FONT
    size = responsive_font_size(FONT_SCALE[key])
    if bold:
        return (family, size, "bold")
    return (family, size)


# --------------------------------------------------------------------------- #
# 主题初始化与切换
# --------------------------------------------------------------------------- #

_THEME_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "theme_academic.json")


def init_appearance() -> None:
    """初始化 customtkinter：跟随系统深/浅色 + 加载墨绿主题。须在创建根窗口前调用。"""
    ctk.set_appearance_mode("System")
    if os.path.exists(_THEME_JSON):
        ctk.set_default_color_theme(_THEME_JSON)
    else:
        # PyInstaller 打包环境兜底（spec 已收集本文件，正常不会走到）
        ctk.set_default_color_theme("green")


def current_mode() -> str:
    """当前实际生效的模式：``"dark"`` 或 ``"light"``。"""
    return ctk.get_appearance_mode().lower()


def is_dark() -> bool:
    return current_mode() == "dark"


def set_appearance(name: str) -> str:
    """手动设置 ``"dark"`` / ``"light"`` / ``"system"``，返回生效后的模式名。"""
    ctk.set_appearance_mode(name)
    return current_mode()


def toggle_appearance() -> str:
    """在深色/浅色之间手动切换，返回新模式名。"""
    return set_appearance("light" if is_dark() else "dark")


# --------------------------------------------------------------------------- #
# 高 DPI
# --------------------------------------------------------------------------- #


def enable_dpi_awareness() -> None:
    """让 Windows 以高分辨率渲染，避免界面模糊。必须在创建根窗口之前调用。"""
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
# 响应式布局基础设施（与主题无关，保持原有行为）
# --------------------------------------------------------------------------- #

_screen_size: "tuple[int, int] | None" = None


def get_screen_size() -> "tuple[int, int]":
    """返回主显示器宽高 (w, h)，缓存结果。"""
    global _screen_size
    if _screen_size is not None:
        return _screen_size
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        w = root.winfo_screenwidth()
        h = root.winfo_screenheight()
        root.destroy()
        _screen_size = (w, h)
    except Exception:
        _screen_size = (1920, 1080)
    return _screen_size


def get_scale_factor() -> float:
    """根据屏幕高度返回缩放因子。"""
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
    """返回自适应窗口尺寸 (w, h)，至少 1100×700。"""
    sw, sh = get_screen_size()
    w = min(1400, int(sw * 0.88))
    h = min(920, int(sh * 0.90))
    w = max(w, 1100)
    h = max(h, 700)
    return (w, h)


def get_responsive_min_size() -> "tuple[int, int]":
    """返回自适应最小窗口尺寸。"""
    _, sh = get_screen_size()
    if sh <= 720:
        return (1000, 620)
    if sh <= 768:
        return (1040, 660)
    return (1100, 700)


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
