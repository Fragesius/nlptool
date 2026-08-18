"""各功能标签页共用的控件工厂与辅助（customtkinter 版）。"""

from __future__ import annotations

import tkinter as tk
from typing import Optional

import customtkinter as ctk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from core import analyzer
from ui import style as s


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #


def clear_widget(w: tk.Widget) -> None:
    for child in w.winfo_children():
        child.destroy()


class Card(ctk.CTkFrame):
    """带小标题的卡片容器（三段式分区的基本单元）。"""

    def __init__(self, parent, title: str = "", **kw):
        kw.setdefault("corner_radius", 10)
        kw.setdefault("fg_color", s.CARD)
        kw.setdefault("border_width", 1)
        kw.setdefault("border_color", s.BORDER)
        super().__init__(parent, **kw)
        self._title_label: Optional[ctk.CTkLabel] = None
        if title:
            self._title_label = ctk.CTkLabel(
                self, text=title,
                font=s.font("headline", bold=True), anchor="w",
            )
            self._title_label.pack(fill="x", padx=12, pady=(10, 0))

    def set_title(self, title: str) -> None:
        if self._title_label is not None:
            self._title_label.configure(text=title)


def accent_btn(parent, text: str, command, **kw) -> ctk.CTkButton:
    """主按钮（墨绿强调色，来自主题）。"""
    kw.setdefault("font", s.font("body", bold=True))
    return ctk.CTkButton(parent, text=text, command=command, **kw)


def flat_btn(parent, text: str, command, **kw) -> ctk.CTkButton:
    """次要按钮（中性灰底）。"""
    kw.setdefault("font", s.font("body"))
    kw.setdefault("fg_color", s.BUTTON_NEUTRAL)
    kw.setdefault("hover_color", s.BUTTON_NEUTRAL_HOVER)
    kw.setdefault("text_color", s.TEXT)
    return ctk.CTkButton(parent, text=text, command=command, **kw)


def hint_label(parent, text: str, **pack_kw) -> ctk.CTkLabel:
    """小号灰色提示文字。"""
    lbl = ctk.CTkLabel(parent, text=text,
                       font=s.font("caption"), text_color=s.MUTED, anchor="w")
    if pack_kw is not None:
        lbl.pack(fill="x", padx=12, **pack_kw)
    return lbl


def make_labeled_text(parent, label: str, mono: bool = True,
                      height: Optional[int] = None) -> ctk.CTkTextbox:
    """创建一个带小标题的 CTkTextbox 面板。"""
    if label:
        ctk.CTkLabel(parent, text=label,
                     font=s.font("footnote"), text_color=s.MUTED,
                     anchor="w").pack(fill="x", padx=12, pady=(6, 0))
    kw = {}
    if height is not None:
        kw["height"] = height
    tb = ctk.CTkTextbox(parent, wrap="word", font=s.font("body", mono=mono), **kw)
    tb.pack(fill="both", expand=True, padx=12, pady=(4, 10))
    return tb


def add_copy_button(parent, getter, label: str = "📋 复制") -> ctk.CTkButton:
    """在结果卡片底部加一个复制按钮：把 getter() 的文本写入剪贴板。"""
    bar = ctk.CTkFrame(parent, fg_color="transparent")
    bar.pack(fill="x", padx=12, pady=(0, 8))
    btn = flat_btn(bar, text=label, width=84, height=26, command=None)

    def _copy() -> None:
        text = getter() or ""
        if not text.strip():
            return
        btn.clipboard_clear()
        btn.clipboard_append(text)
        btn.configure(text="✓ 已复制")
        btn.after(1500, lambda: btn.configure(text=label))

    btn.configure(command=_copy)
    btn.pack(side="right")
    return btn


def textbox_getter(tb: ctk.CTkTextbox):
    """返回读取 CTkTextbox 全部内容的 getter。"""
    return lambda: tb.get("1.0", "end-1c")


def embed_figure(parent: tk.Widget, fig: Figure) -> None:
    """将 matplotlib Figure 嵌入可滚动容器中。"""
    # 关闭所有旧 Figure，防止内存泄漏
    plt.close("all")
    clear_widget(parent)

    holder = ctk.CTkScrollableFrame(parent, fg_color="transparent")
    holder.pack(fill="both", expand=True)

    mpl_canvas = FigureCanvasTkAgg(fig, master=holder)
    mpl_canvas.draw()
    mpl_canvas.get_tk_widget().pack(fill="both", expand=True)


def _ner_status_msg(lang: str | None) -> str:
    lang = lang or analyzer.detect_language("")
    if lang == "zh":
        spa_ok = bool(analyzer._get_spacy("zh"))
    else:
        spa_ok = bool(analyzer._get_spacy("en"))
    if not spa_ok:
        model = "zh_core_web_sm" if lang == "zh" else "en_core_web_sm"
        return (
            f"⚠ 未安装 spaCy {model} 模型，无法进行命名实体识别。\n"
            f"安装：python -m spacy download {model}"
        )
    return (
        "未识别到命名实体：当前文本中可能没有人名、地名、机构名等专有名词。\n"
        "可尝试输入「苹果公司总部位于北京，由陈小明担任CEO」这类含实体的句子。"
    )


def _dep_status_msg(lang: str | None) -> str:
    lang = lang or "en"
    if lang == "zh":
        spa_ok = bool(analyzer._get_spacy("zh"))
    else:
        spa_ok = bool(analyzer._get_spacy("en"))
    if not spa_ok:
        model = "zh_core_web_sm" if lang == "zh" else "en_core_web_sm"
        return (
            f"⚠ 未安装 spaCy {model} 模型，无法进行依存句法分析。\n"
            f"安装：python -m spacy download {model}"
        )
    return "未生成依存数据：请确认文本语言与模型匹配（英文用 en_core_web_sm）。"
