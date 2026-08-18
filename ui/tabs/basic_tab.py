"""基础分析标签页（customtkinter 版）。"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import Optional

import customtkinter as ctk

from core import analyzer, history
from ui.async_runner import TaskRunner
from ui import style as s
from ui.style import is_compact_mode
from ui.tabs.widgets import (
    Card, accent_btn, flat_btn,
    make_labeled_text, add_copy_button, textbox_getter,
)


# --------------------------------------------------------------------------- #
# 基础分析
# --------------------------------------------------------------------------- #


class BasicTab(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._runner = TaskRunner(self)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ── 运行控制 ──
        ctrl_card = Card(self, "▶ 运行控制")
        ctrl_card.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        ctrl = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        ctrl.pack(fill="x", padx=12, pady=(6, 10))
        accent_btn(ctrl, text="▶ 运行基础分析", command=self.run).pack(side="left")
        self.export_btn = flat_btn(ctrl, text="📤 导出结果", command=self.export,
                                   state="disabled")
        self.export_btn.pack(side="left", padx=(8, 0))

        # ── 结果展示：统计摘要 ──
        card = Card(self, "📋 统计摘要")
        card.grid(row=1, column=0, sticky="ew", padx=10, pady=4)
        summary_h = 90 if is_compact_mode() else 120
        self.summary = make_labeled_text(card, "", height=summary_h)
        add_copy_button(card, textbox_getter(self.summary))

        # ── 结果展示：分词 + 词频 双栏 ──
        result_card = Card(self, "🔤 分词与词频")
        result_card.grid(row=2, column=0, sticky="nsew", padx=10, pady=4)
        cols = ctk.CTkFrame(result_card, fg_color="transparent")
        cols.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        cols.grid_columnconfigure(0, weight=1)
        cols.grid_columnconfigure(1, weight=1)
        cols.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(cols, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(4, 2))
        right = ctk.CTkFrame(cols, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(2, 4))

        self.tokens_text = make_labeled_text(
            left, "🔤 分词结果  —  词元 / 词性 / 词形还原"
        )
        self.freq_text = make_labeled_text(right, "📊 词频 Top 30")

        # ── 关键词上下文 KWIC ──
        kwic_card = Card(self, "🔍 关键词上下文 (KWIC)")
        kwic_card.grid(row=3, column=0, sticky="ew", padx=10, pady=(4, 10))

        kwic_ctrl = ctk.CTkFrame(kwic_card, fg_color="transparent")
        kwic_ctrl.pack(fill="x", padx=12, pady=(8, 4))
        ctk.CTkLabel(kwic_ctrl, text="检索词：", font=s.font("body")).pack(side="left")
        self.kwic_entry = ctk.CTkEntry(kwic_ctrl, width=160, font=s.font("body"))
        self.kwic_entry.pack(side="left", padx=(4, 8))
        ctk.CTkLabel(kwic_ctrl, text="窗口：", font=s.font("body")).pack(side="left")
        self.kwic_window = tk.StringVar(value="6")
        ctk.CTkOptionMenu(
            kwic_ctrl, variable=self.kwic_window,
            values=[str(i) for i in range(2, 13)],
            width=64, font=s.font("body"),
        ).pack(side="left", padx=(4, 8))
        self.kwic_regex = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(kwic_ctrl, text="正则", variable=self.kwic_regex,
                        font=s.font("body")).pack(side="left", padx=(0, 8))
        self.kwic_case = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(kwic_ctrl, text="区分大小写", variable=self.kwic_case,
                        font=s.font("body")).pack(side="left", padx=(0, 8))
        flat_btn(kwic_ctrl, text="🔍 搜索", command=self.run_kwic).pack(side="left")
        self.kwic_export_btn = flat_btn(kwic_ctrl, text="📤 导出 KWIC",
                                        command=self.export_kwic, state="disabled")
        self.kwic_export_btn.pack(side="left", padx=(8, 0))

        self.kwic_text = make_labeled_text(kwic_card, "", height=140)
        add_copy_button(kwic_card, textbox_getter(self.kwic_text))
        self._kwic_last: list = []

        self._last: Optional[analyzer.BasicResult] = None

    def run(self) -> None:
        text = self.app.get_text()
        if not text.strip():
            messagebox.showinfo("提示", "请先输入待分析文本。")
            return
        if self._runner.is_running():
            return

        lang = self.app.get_lang()
        self.app.set_status("正在执行基础分析……")
        self._runner.run(
            analyzer.analyze_basic,
            args=(text, lang),
            on_success=self._on_result,
            on_error=self._on_error,
            title="基础分析",
            message="正在分词、统计词频与词性分布...",
        )

    def _on_result(self, res: analyzer.BasicResult) -> None:
        self._last = res

        self.summary.delete("1.0", "end")
        self.summary.insert("end", res.summary())

        self.tokens_text.delete("1.0", "end")
        for t in res.tokens:
            if not t.text.strip():
                continue
            self.tokens_text.insert("end", f"{t.text:<20s}{t.pos:<8s}{t.lemma}\n")

        self.freq_text.delete("1.0", "end")
        for w, c in res.freq.most_common(30):
            self.freq_text.insert("end", f"{w:<24s}{c}\n")

        self.export_btn.configure(state="normal")
        self._save_history(res)
        self.app.set_status(
            f"基础分析完成 — {res.word_count} 词元, {res.sentence_count} 句子"
        )

    def _on_error(self, e: Exception) -> None:
        messagebox.showerror("错误", f"分析失败：{e}")
        self.app.set_status("分析失败")

    def export(self) -> None:
        if self._last is None:
            return
        from core.export import export_basic_result
        export_basic_result(self._last, self.winfo_toplevel())

    def run_kwic(self) -> None:
        keyword = self.kwic_entry.get().strip()
        if not keyword:
            messagebox.showinfo("提示", "请输入检索词。")
            return
        text = self.app.get_text()
        if not text.strip():
            messagebox.showinfo("提示", "请先输入待分析文本。")
            return
        try:
            window = int(self.kwic_window.get())
        except ValueError:
            window = 6
        from core.concordance import kwic, kwic_summary
        lines = kwic(
            text, keyword,
            lang=self.app.get_lang(),
            window=window,
            case_sensitive=self.kwic_case.get(),
            regex=self.kwic_regex.get(),
        )
        self._kwic_last = lines
        self.kwic_text.delete("1.0", "end")
        self.kwic_text.insert("end", kwic_summary(lines))
        self.kwic_export_btn.configure(state="normal" if lines else "disabled")
        self.app.set_status(f"KWIC 搜索完成 — {len(lines)} 条匹配")

    def export_kwic(self) -> None:
        if not self._kwic_last:
            return
        from core.export import export_kwic_result
        export_kwic_result(self._kwic_last, self.winfo_toplevel())

    def _save_history(self, res: analyzer.BasicResult) -> None:
        try:
            lang_name = res.lang_name()
            entry = history.build_entry(
                text=self.app.get_text(),
                lang=lang_name,
                basic_summary=res.summary(),
                tokens_preview=", ".join(
                    t.text for t in res.tokens[:20] if t.text.strip()
                ),
                freq_preview=", ".join(
                    f"{w}({c})" for w, c in res.freq.most_common(10)
                ),
            )
            history.add_entry(entry)
        except Exception:
            pass

    def get_last(self) -> Optional[analyzer.BasicResult]:
        return self._last
