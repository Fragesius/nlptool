"""历史记录标签页（customtkinter 版）。"""

from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from core import history
from ui import style as s
from ui.style import is_compact_mode
from ui.tabs.widgets import (
    clear_widget, Card, flat_btn,
    make_labeled_text, add_copy_button, textbox_getter,
)


# --------------------------------------------------------------------------- #
# 历史记录
# --------------------------------------------------------------------------- #


class HistoryTab(ctk.CTkFrame):
    """展示过往分析记录，点击可回溯输入文本。"""

    _COLUMNS = (
        ("时间", 150),
        ("语言", 60),
        ("输入摘要", 230),
        ("关键词 / 实体", 250),
        ("情感", 90),
    )

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── 运行控制 ──
        ctrl_card = Card(self, "▶ 操作")
        ctrl_card.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        ctrl = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        ctrl.pack(fill="x", padx=12, pady=(6, 10))
        flat_btn(ctrl, text="🔄 刷新列表", command=self.refresh).pack(side="left")
        flat_btn(ctrl, text="🗑 清空历史", command=self.clear).pack(side="left", padx=8)
        ctk.CTkLabel(
            ctrl,
            text="单击记录查看详情，点击「📥」将其文本载入主输入框",
            font=s.font("footnote"), text_color=s.MUTED,
        ).pack(side="left", padx=12)

        # ── 记录列表 ──
        list_card = Card(self, "📜 历史记录")
        list_card.grid(row=1, column=0, sticky="nsew", padx=10, pady=4)

        hdr = ctk.CTkFrame(list_card, fg_color=s.BUTTON_NEUTRAL, corner_radius=6)
        hdr.pack(fill="x", padx=12, pady=(6, 2))
        for text, w in self._COLUMNS:
            ctk.CTkLabel(hdr, text=text, width=w, anchor="w",
                         font=s.font("caption", bold=True),
                         text_color=s.MUTED).pack(side="left", padx=4)
        ctk.CTkLabel(hdr, text="", width=60).pack(side="left", padx=4)

        self._list_body = ctk.CTkScrollableFrame(list_card, fg_color="transparent")
        self._list_body.pack(fill="both", expand=True, padx=4, pady=(0, 8))

        # ── 详情面板 ──
        detail_card = Card(self, "📋 记录详情")
        detail_card.grid(row=2, column=0, sticky="ew", padx=10, pady=(4, 10))
        detail_h = 100 if is_compact_mode() else 150
        self.detail = make_labeled_text(detail_card, "", mono=False, height=detail_h)
        add_copy_button(detail_card, textbox_getter(self.detail))

        self._entries: list[history.HistoryEntry] = []
        self.refresh()

    def refresh(self) -> None:
        self._entries = history.load_all()
        self._entries.reverse()
        clear_widget(self._list_body)
        for e in self._entries:
            self._add_row(e)

    def _add_row(self, e: "history.HistoryEntry") -> None:
        lang = e.lang[:8] if e.lang else "-"
        inp = e.input_text.replace("\n", " ")[:60]
        previews = []
        if e.keywords_preview:
            previews.append(e.keywords_preview[:80])
        if e.ner_preview:
            previews.append(e.ner_preview[:80])
        kw_or_ner = " | ".join(previews) if previews else "-"
        sent = "-"
        if e.sentiment_label:
            sent = f"{e.sentiment_label} {e.sentiment_score:+.2f}"

        row = ctk.CTkFrame(self._list_body, fg_color="transparent")
        row.pack(fill="x", pady=1)

        # CTkButton 内部用 grid 管理子控件，不能再 pack 内容；
        # 行本体用 CTkFrame + 点击绑定实现"整行可点"。
        inner = ctk.CTkFrame(row, fg_color="transparent")
        inner.pack(side="left", fill="x", expand=True)
        inner.bind("<Button-1>", lambda _ev, ent=e: self._show_detail(ent))
        for text, w in zip((e.timestamp[:19], lang, inp, kw_or_ner, sent),
                           [c[1] for c in self._COLUMNS]):
            lbl = ctk.CTkLabel(inner, text=text, width=w, anchor="w",
                               font=s.font("footnote"))
            lbl.pack(side="left", padx=4)
            lbl.bind("<Button-1>", lambda _ev, ent=e: self._show_detail(ent))

        flat_btn(row, text="📥", width=40, height=26,
                 command=lambda ent=e: self._load_entry(ent)).pack(side="right", padx=4)

    def clear(self) -> None:
        if messagebox.askyesno("确认", "确定清空全部历史记录？此操作不可撤销。"):
            history.clear_all()
            self.refresh()
            self.detail.delete("1.0", "end")

    def _show_detail(self, entry: "history.HistoryEntry") -> None:
        self.detail.delete("1.0", "end")
        detail_lines = []
        if entry.basic_summary:
            detail_lines.append(f"▎基础分析\n{entry.basic_summary}\n")
        if entry.tokens_preview:
            detail_lines.append(f"▎分词示例: {entry.tokens_preview}\n")
        if entry.freq_preview:
            detail_lines.append(f"▎高频词: {entry.freq_preview}\n")
        if entry.keywords_preview:
            detail_lines.append(f"▎关键词: {entry.keywords_preview}\n")
        if entry.ner_preview:
            detail_lines.append(f"▎命名实体: {entry.ner_preview}\n")
        if entry.sentiment_label:
            detail_lines.append(f"▎情感: {entry.sentiment_label} ({entry.sentiment_score:+.2f})\n")
        self.detail.insert("end", "\n".join(detail_lines) if detail_lines else "（无分析记录）")

    def _load_entry(self, entry: "history.HistoryEntry") -> None:
        # 载入输入文本
        self.app.text.delete("1.0", "end")
        self.app.text.insert("end", entry.input_text)
        self.app._set_input_color(False)
        self.app._placeholder_shown = False
        # 根据语言设置下拉
        lang_map = {"中文": "中文", "英文": "英文", "中英混合": "中英混合"}
        self.app.lang_var.set(lang_map.get(entry.lang, "自动"))
        # 显示详情
        self._show_detail(entry)
        self.app.set_status(f"已载入历史记录 — {entry.timestamp[:19]}")
