"""对比分析标签页（customtkinter 版）。"""

from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from core import analyzer, comparison
from ui.async_runner import TaskRunner
from ui import style as s
from ui.tabs.widgets import (
    Card, accent_btn, flat_btn,
    make_labeled_text, add_copy_button, textbox_getter,
)


# --------------------------------------------------------------------------- #
# 对比分析
# --------------------------------------------------------------------------- #


class CompareTab(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._runner = TaskRunner(self)
        self._last_readability = None
        self._last_alignment = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ── 输入设置：双输入框 ──
        input_card = Card(self, "📝 对比文本输入")
        input_card.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 4))
        cols = ctk.CTkFrame(input_card, fg_color="transparent")
        cols.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        cols.grid_columnconfigure(0, weight=1)
        cols.grid_columnconfigure(1, weight=1)
        cols.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(cols, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(4, 2))
        right = ctk.CTkFrame(cols, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(2, 4))

        self.zh_box = make_labeled_text(left, "中文原文")
        self.en_box = make_labeled_text(right, "英文原文")

        # ── 运行控制 ──
        ctrl_card = Card(self, "▶ 运行控制")
        ctrl_card.grid(row=1, column=0, sticky="ew", padx=10, pady=4)
        ctrl = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        ctrl.pack(fill="x", padx=12, pady=(6, 10))
        accent_btn(ctrl, text="▶ 分析可读性",
                   command=self.run_readability).pack(side="left")
        self.export_read_btn = flat_btn(ctrl, text="📤 导出可读性",
                                        command=self.export_readability,
                                        state="disabled")
        self.export_read_btn.pack(side="left", padx=(8, 16))
        flat_btn(ctrl, text="🔗 对齐中英句子",
                 command=self.run_align).pack(side="left")
        self.export_align_btn = flat_btn(ctrl, text="📤 导出对齐",
                                         command=self.export_alignment,
                                         state="disabled")
        self.export_align_btn.pack(side="left", padx=(8, 0))
        flat_btn(ctrl, text="📥 从主输入框填入",
                 command=self.fill_from_main).pack(side="left", padx=(8, 0))

        # ── 结果展示 ──
        out_card = Card(self, "📋 结果输出")
        out_card.grid(row=2, column=0, sticky="nsew", padx=10, pady=(4, 10))
        self.out = make_labeled_text(out_card, "")
        add_copy_button(out_card, textbox_getter(self.out))

    def run_readability(self) -> None:
        text = self.app.get_text()
        if not text.strip():
            messagebox.showinfo("提示", "请先输入待分析文本。")
            return
        if self._runner.is_running():
            return

        lang = self.app.get_lang()
        self.app.set_status("正在计算可读性……")
        self._runner.run(
            comparison.readability_for,
            args=(text, lang),
            on_success=self._on_readability_result,
            on_error=self._on_error,
            title="可读性分析",
            message="正在计算可读性指标...",
        )

    def _on_readability_result(self, res) -> None:
        self._last_readability = res
        self.out.delete("1.0", "end")
        self.out.insert("end", res.summary() + "\n")
        self.export_read_btn.configure(state="normal")
        self.app.set_status("可读性分析完成")

    def export_readability(self) -> None:
        if self._last_readability is None:
            return
        from core.export import export_readability_result
        export_readability_result(self._last_readability, self.winfo_toplevel())

    def fill_from_main(self) -> None:
        text = self.app.get_text()
        lang = analyzer.detect_language(text)
        if lang == "en":
            self.en_box.delete("1.0", "end")
            self.en_box.insert("end", text)
        else:
            self.zh_box.delete("1.0", "end")
            self.zh_box.insert("end", text)

    def run_align(self) -> None:
        zh = self.zh_box.get("1.0", "end").strip()
        en = self.en_box.get("1.0", "end").strip()
        if not zh or not en:
            messagebox.showinfo("提示", "请在中英文框中均输入文本。")
            return
        if self._runner.is_running():
            return

        self.app.set_status("正在对齐中英句子……")
        self._runner.run(
            comparison.align_zh_en,
            args=(zh, en),
            on_success=self._on_alignment_result,
            on_error=self._on_error,
            title="中英对齐",
            message="正在按句子序号启发式对齐...",
        )

    def _on_alignment_result(self, res) -> None:
        self._last_alignment = res
        self.out.delete("1.0", "end")
        self.out.insert("end", res.summary() + "\n\n")
        for i, (z, e) in enumerate(res.pairs, 1):
            self.out.insert("end", f"[{i}] {z}\n    {e}\n\n")
        self.export_align_btn.configure(state="normal")
        self.app.set_status(f"对齐完成 — {len(res.pairs)} 句对")

    def export_alignment(self) -> None:
        if self._last_alignment is None:
            return
        from core.export import export_alignment_result
        export_alignment_result(self._last_alignment, self.winfo_toplevel())

    def _on_error(self, e: Exception) -> None:
        messagebox.showerror("错误", f"分析失败：{e}")
        self.app.set_status("分析失败")
