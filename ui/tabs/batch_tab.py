"""批量处理标签页（customtkinter 版）。"""

from __future__ import annotations

import os
from tkinter import messagebox, filedialog

import customtkinter as ctk

from core import batch, file_io
from ui.async_runner import TaskRunner
from ui import style as s
from ui.tabs.widgets import (
    clear_widget, Card, accent_btn, flat_btn, add_copy_button,
)


# --------------------------------------------------------------------------- #
# 批量处理
# --------------------------------------------------------------------------- #


class BatchTab(ctk.CTkFrame):
    """批量分析多个文件，输出聚合统计表格。"""

    _COLUMNS = (
        ("文件名", 180),
        ("状态", 50),
        ("语言", 60),
        ("字符数", 70),
        ("词元数", 70),
        ("句子数", 70),
        ("不重复词", 70),
        ("Top 词", 220),
    )

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._runner = TaskRunner(self)
        self._results: list = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── 运行控制 ──
        ctrl_card = Card(self, "▶ 运行控制")
        ctrl_card.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        ctrl = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        ctrl.pack(fill="x", padx=12, pady=(6, 10))
        flat_btn(ctrl, text="📂 选择文件", command=self.select_files).pack(side="left")
        accent_btn(ctrl, text="▶ 开始批量分析",
                   command=self.run).pack(side="left", padx=(8, 0))
        self.export_btn = flat_btn(ctrl, text="📤 导出结果", command=self.export,
                                   state="disabled")
        self.export_btn.pack(side="left", padx=(8, 0))

        # ── 结果展示：文件列表 + 结果表格 ──
        table_card = Card(self, "📋 批量分析结果")
        table_card.grid(row=1, column=0, sticky="nsew", padx=10, pady=(4, 10))

        hdr = ctk.CTkFrame(table_card, fg_color=s.BUTTON_NEUTRAL, corner_radius=6)
        hdr.pack(fill="x", padx=12, pady=(6, 2))
        for text, w in self._COLUMNS:
            ctk.CTkLabel(hdr, text=text, width=w, anchor="w",
                         font=s.font("caption", bold=True),
                         text_color=s.MUTED).pack(side="left", padx=4)

        self._list_body = ctk.CTkScrollableFrame(table_card, fg_color="transparent")
        self._list_body.pack(fill="both", expand=True, padx=4, pady=(0, 8))
        add_copy_button(table_card, lambda: self._report_text)

        self._files: list[str] = []
        self._report_text = ""

    def _add_row(self, values: tuple) -> None:
        row = ctk.CTkFrame(self._list_body, fg_color="transparent")
        row.pack(fill="x", pady=1)
        for text, (_, w) in zip(values, self._COLUMNS):
            ctk.CTkLabel(row, text=str(text), width=w, anchor="w",
                         font=s.font("footnote")).pack(side="left", padx=4)

    def select_files(self) -> None:
        paths = filedialog.askopenfilenames(filetypes=file_io.FILETYPES)
        if not paths:
            return
        self._files = list(paths)
        self._refresh_list()
        self.app.set_status(f"已选择 {len(self._files)} 个文件")

    def _refresh_list(self) -> None:
        clear_widget(self._list_body)
        for p in self._files:
            self._add_row((os.path.basename(p), "待分析", "", "", "", "", "", ""))

    def run(self) -> None:
        if not self._files:
            messagebox.showinfo("提示", "请先选择文件。")
            return
        if self._runner.is_running() and not self._runner.is_cancelling():
            return

        self.export_btn.configure(state="disabled")
        self.app.set_status("正在批量分析文件……")
        self._runner.run(
            batch.analyze_files,
            args=(self._files, self.app.get_lang()),
            kwargs={"cancel_check": self._runner.check_cancelled},
            on_success=self._on_result,
            on_error=self._on_error,
            on_cancel=self._on_cancel,
            title="批量分析",
            message=f"正在分析 {len(self._files)} 个文件，请稍候...",
        )

    def _on_result(self, results: list) -> None:
        self._results = results
        clear_widget(self._list_body)
        lines = ["\t".join(name for name, _ in self._COLUMNS)]
        for item in results:
            if item.status == "ok":
                top = ", ".join(f"{w}({c})" for w, c in item.top_words)
                values = (
                    item.filename, "✓", item.lang,
                    item.char_count, item.word_count, item.sentence_count,
                    item.unique_words, top,
                )
            else:
                values = (item.filename, "✗", "", "", "", "", "", item.error)
            self._add_row(values)
            lines.append("\t".join(str(v) for v in values))
        self._report_text = "\n".join(lines)

        ok_count = sum(1 for r in results if r.status == "ok")
        self.export_btn.configure(state="normal")
        self.app.set_status(f"批量分析完成 — {ok_count}/{len(results)} 成功")

    def _on_cancel(self) -> None:
        """用户取消批量分析：复位状态。"""
        self.app.set_status("批量分析已取消")

    def _on_error(self, e: Exception) -> None:
        messagebox.showerror("错误", f"批量分析失败：{e}")
        self.app.set_status("批量分析失败")

    def export(self) -> None:
        if not self._results:
            return
        from core.export import export_batch_result
        export_batch_result(self._results, self.winfo_toplevel())
