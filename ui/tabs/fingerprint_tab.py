"""语言指纹分析标签页（customtkinter 版）。"""

from __future__ import annotations

import re
import tkinter as tk
from tkinter import messagebox, filedialog
from typing import Optional

import customtkinter as ctk

from core import linguistic_fingerprint
from ui.async_runner import TaskRunner
from ui import style as s
from ui.style import is_compact_mode, get_screen_size
from ui.tabs.widgets import (
    Card, accent_btn, flat_btn, hint_label,
    add_copy_button, textbox_getter, embed_figure,
)


# --------------------------------------------------------------------------- #
# 语言指纹分析
# --------------------------------------------------------------------------- #


class _InputRow:
    """一个紧凑的文本输入行：文件选择按钮 + 粘贴按钮 + 状态标签。"""

    def __init__(
        self,
        parent: tk.Widget,
        label: str,
        icon: str,
        min_chars: int = 0,      # 最小字符数（用于 A 的 3000 限制）
        on_change: "callable | None" = None,
    ) -> None:
        self.label = label
        self.icon = icon
        self.min_chars = min_chars
        self.on_change = on_change
        self._text = ""        # 存储已加载的文本

        self.frame = Card(parent, f"{icon} {label}")
        self.frame.pack(fill="x", padx=10, pady=(3, 2))

        inner = ctk.CTkFrame(self.frame, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=(6, 10))

        self.file_btn = flat_btn(inner, text="📂 选择文件", width=100,
                                 command=self._load_file)
        self.file_btn.pack(side="left", padx=(0, 4))

        self.paste_btn = flat_btn(inner, text="📋 粘贴文本", width=100,
                                  command=self._paste_text)
        self.paste_btn.pack(side="left", padx=(0, 8))

        self.status_label = ctk.CTkLabel(
            inner, text="未加载文本",
            font=s.font("footnote"), text_color=s.MUTED,
        )
        self.status_label.pack(side="left")

        self.clear_btn = flat_btn(inner, text="✕", width=36,
                                  command=self._clear)
        self.clear_btn.pack(side="right")

    # ── 文件加载 ──
    def _load_file(self) -> None:
        from core import file_io as fio

        path = filedialog.askopenfilename(filetypes=fio.FILETYPES)
        if not path:
            return
        try:
            text, label_text = fio.read_file_with_label(path)
            if not text.strip():
                self.status_label.configure(text="⚠ 文件为空", text_color=s.DANGER)
                return
            self._text = text
            self.status_label.configure(text=label_text, text_color=s.SUCCESS)
            if self.on_change:
                self.on_change()
        except Exception as e:
            messagebox.showerror("读取失败", str(e))

    # ── 粘贴文本 ──
    def _paste_text(self) -> None:
        """弹出粘贴窗口。按 Enter 确认，Shift+Enter 换行。"""
        popup = ctk.CTkToplevel(self.frame)
        popup.title(f"粘贴文本 — {self.label}")
        # 响应式尺寸
        _, sh = get_screen_size()
        pw, ph = (580, 340) if sh <= 768 else (720, 420)
        popup.geometry(f"{pw}x{ph}")
        popup.minsize(480, 280)
        popup.transient(self.frame.winfo_toplevel())
        popup.grab_set()

        box = ctk.CTkTextbox(popup, wrap="word", font=s.font("headline"))
        box.pack(fill="both", expand=True, padx=8, pady=8)
        # 预填已有文本
        if self._text:
            box.insert("1.0", self._text)

        btn_frame = ctk.CTkFrame(popup, fg_color="transparent")
        btn_frame.pack(fill="x", padx=8, pady=(0, 8))

        # 提示文字
        ctk.CTkLabel(
            btn_frame, text="按 Enter 确认  ·  Shift+Enter 换行",
            font=s.font("caption"), text_color=s.MUTED,
        ).pack(side="left", padx=(0, 8))

        def _confirm(event=None):
            text = box.get("1.0", "end-1c").strip()
            self._text = text
            count = len(re.sub(r"\s", "", text))
            warn = ""
            if self.min_chars > 0 and 0 < count < self.min_chars:
                warn = f"  ⚠ 不足 {self.min_chars} 字符"
            self.status_label.configure(
                text=f"📋 手动粘贴  —  {count:,} 字符{warn}",
                text_color=s.DANGER if warn else s.SUCCESS,
            )
            if self.on_change:
                self.on_change()
            popup.destroy()

        def _shift_return(event):
            """Shift+Enter 插入换行，不提交。"""
            box.insert("insert", "\n")
            return "break"

        # 绑定键盘快捷键
        box.bind("<Return>", _confirm)
        box.bind("<Shift-Return>", _shift_return)

        accent_btn(btn_frame, text="✅ 确认", width=90,
                   command=_confirm).pack(side="right", padx=4)
        flat_btn(btn_frame, text="取消", width=80,
                 command=popup.destroy).pack(side="right")

    # ── 清除 ──
    def _clear(self) -> None:
        self._text = ""
        self.status_label.configure(text="未加载文本", text_color=s.MUTED)
        if self.on_change:
            self.on_change()

    # ── 公共 API ──
    def get_text(self) -> str:
        return self._text

    def set_text(self, text: str, label: str = "") -> None:
        """直接设置文本（供程序调用）。"""
        self._text = text
        count = len(re.sub(r"\s", "", text))
        self.status_label.configure(
            text=label if label else f"已设置  —  {count:,} 字符",
            text_color=s.SUCCESS,
        )

    def destroy(self) -> None:
        self.frame.destroy()


class _ControlRow(_InputRow):
    """对照作者的输入行（带移除按钮）。"""

    def __init__(
        self,
        parent: tk.Widget,
        index: int,
        on_remove: "callable",
    ) -> None:
        super().__init__(parent, f"对照作者 C{index}", "🔍")
        self.index = index
        self.on_remove_cb = on_remove

        # 把清除按钮换成移除按钮
        self.clear_btn.configure(command=self._remove)

    def _remove(self) -> None:
        self.destroy()
        self.on_remove_cb(self)

    def redraw(self, new_index: int) -> None:
        self.index = new_index
        self.frame.set_title(f"🔍 对照作者 C{new_index}")


# ── FingerprintTab ──────────────────────────────────────────


class FingerprintTab(ctk.CTkFrame):
    """语言指纹分析标签页。

    左右双栏布局：左侧=相似度图与详细报告，右侧=输入设置与运行控制。
    """

    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.control_rows: list[_ControlRow] = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0, minsize=420)
        self.grid_rowconfigure(0, weight=1)

        # ══ 左栏：结果展示（图表 + 报告）══
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 4), pady=10)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)

        # ══ 右栏：输入设置 + 运行控制（可滚动）══
        right = ctk.CTkScrollableFrame(self, fg_color="transparent", width=400)
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 10), pady=10)

        # ── 运行控制 ──
        ctrl_card = Card(right, "▶ 运行控制")
        ctrl_card.pack(fill="x", padx=6, pady=(4, 4))
        ctrl = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        ctrl.pack(fill="x", padx=12, pady=(6, 10))
        self.run_btn = accent_btn(ctrl, text="▶ 运行语言指纹分析",
                                  command=self.run)
        self.run_btn.pack(side="left")
        self.export_btn = flat_btn(ctrl, text="📤 导出报告", command=self.export,
                                   state="disabled")
        self.export_btn.pack(side="left", padx=(8, 0))
        self.cancel_btn = flat_btn(ctrl, text="⏹ 取消", command=self._cancel_run,
                                   state="disabled")
        self.cancel_btn.pack(side="left", padx=(8, 0))
        # 内嵌确定性进度条（与批量实验页同款，不弹模态对话框）
        self.progress_bar = ctk.CTkProgressBar(ctrl_card, mode="determinate")
        self.progress_bar.pack(fill="x", padx=12, pady=(0, 4))
        self.progress_bar.set(0)
        self._runner = TaskRunner(self)
        self._last: Optional[linguistic_fingerprint.FingerprintResult] = None
        hint_label(
            ctrl_card,
            "支持加载文件或直接粘贴文本（txt / docx / pdf / html / rtf 等）",
            pady=(0, 8),
        )

        # ── 输入设置：可疑文本 A ──
        self.row_a = _InputRow(
            right, "可疑文本 A（≥3000 字符）", "📝", min_chars=3000,
            on_change=self._update_status,
        )

        # ── 嫌疑作者 B ──
        self.row_b = _InputRow(
            right, "嫌疑作者 B 的已知作品", "👤", on_change=self._update_status,
        )

        # ── 对照作者容器 ──
        self.controls_container = ctk.CTkFrame(right, fg_color="transparent")
        self.controls_container.pack(fill="x", padx=0, pady=0)

        # 添加对照按钮
        add_frame = ctk.CTkFrame(right, fg_color="transparent")
        add_frame.pack(fill="x", padx=10, pady=(2, 4))
        self.add_btn = flat_btn(add_frame, text="+ 添加对照作者",
                                command=self._add_control)
        self.add_btn.pack(side="left")
        ctk.CTkLabel(
            add_frame,
            text="  建议选同性别、同类型、同时期的作家",
            font=s.font("caption"), text_color=s.MUTED,
        ).pack(side="left", padx=6)

        # 默认添加一个对照
        self._add_control()

        # ── 结果展示：图表区域 ──
        self.chart_frame = Card(left, "📊 相似度对比图")
        self.chart_frame.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.chart_holder = ctk.CTkFrame(self.chart_frame, fg_color="transparent",
                                         height=260)
        self.chart_holder.pack(fill="x", padx=8, pady=8)
        self.chart_holder.pack_propagate(False)

        # ── 结果展示：详细报告 ──
        self.report_frame = Card(left, "📋 详细报告")
        self.report_frame.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        self.results_text = ctk.CTkTextbox(
            self.report_frame, wrap="word",
            font=s.font("footnote" if is_compact_mode() else "body"),
        )
        self.results_text.pack(fill="both", expand=True, padx=12, pady=(4, 4))
        add_copy_button(self.report_frame, textbox_getter(self.results_text))
        # 初始提示
        self.results_text.insert(
            "end",
            "请加载文本后点击「▶ 运行语言指纹分析」开始分析。\n\n"
            "支持的文件格式：TXT / DOCX / PDF / HTML / MD / RTF / JSON / CSV / XML\n\n"
            "使用提示：\n"
            "  · 可疑文本 A 至少需要 3000 字符（不含空白）\n"
            "  · 嫌疑作者 B 的文本越多越好，建议 5000+ 字符\n"
            "  · 对照作者应选择同性别、同类型、同时期的作家\n"
            "  · 点击「📋 粘贴文本」可在弹窗中直接粘贴或编辑文本\n",
        )

    # ── 状态更新 ──
    @staticmethod
    def _count_chars(text: str) -> int:
        """统计不含空白字符的字符数。"""
        return len(re.sub(r"\s", "", text))

    def _update_status(self) -> None:
        """输入变化时更新状态栏。"""
        a_count = self._count_chars(self.row_a.get_text())
        b_count = self._count_chars(self.row_b.get_text())
        n_controls = sum(1 for r in self.control_rows if r.get_text().strip())
        ready = a_count >= 3000 and b_count > 0 and n_controls >= 1
        status = "✅ 就绪，可以运行" if ready else "⏳ 等待更多输入"
        self.app.set_status(f"{status}  |  A:{a_count}字  B:{b_count}字  对照:{n_controls}个")

    # ── 动态对照行 ──
    def _add_control(self) -> None:
        if len(self.control_rows) >= 3:
            return
        idx = len(self.control_rows) + 1
        row = _ControlRow(self.controls_container, idx, self._on_remove_control)
        self.control_rows.append(row)
        self._update_add_button()

    def _on_remove_control(self, row: _ControlRow) -> None:
        self.control_rows.remove(row)
        for i, r in enumerate(self.control_rows, 1):
            r.redraw(i)
        self._update_add_button()

    def _update_add_button(self) -> None:
        if len(self.control_rows) >= 3:
            self.add_btn.configure(state="disabled")
        else:
            self.add_btn.configure(state="normal")

    # ── 运行分析 ──
    def run(self) -> None:
        # 防重入：分析期间禁用按钮；上个任务已取消（线程退出中）时允许立即重启
        if self._runner.is_running() and not self._runner.is_cancelling():
            return

        suspect = self.row_a.get_text().strip()
        author_b = self.row_b.get_text().strip()
        controls = [r.get_text().strip() for r in self.control_rows]
        controls = [c for c in controls if c]

        # 验证（在主线程弹窗）
        a_len = self._count_chars(suspect)
        if a_len < 3000:
            messagebox.showwarning(
                "提示", f"可疑文本 A 仅 {a_len} 个字符，需要至少 3000 个字符。"
            )
            return
        if not author_b:
            messagebox.showwarning("提示", "请提供嫌疑作者 B 的已知作品。")
            return
        if not controls:
            messagebox.showwarning("提示", "请至少提供 1 个对照作者文本。")
            return

        self.run_btn.configure(state="disabled")
        self.export_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.progress_bar.set(0)
        self.app.set_status("正在运行语言指纹分析……")
        self.results_text.delete("1.0", "end")
        self.results_text.insert("end", "⏳ 分析中，请稍候……\n")

        self._runner.run(
            linguistic_fingerprint.analyze_fingerprint,
            args=(suspect, author_b, controls, self.app.get_lang()),
            kwargs={
                "progress_callback": self._on_run_progress,
                "cancel_check": self._runner.check_cancelled,
            },
            on_success=lambda res: self._on_result(res, a_len, author_b, controls),
            on_error=self._on_error,
            on_cancel=self._on_cancel,
            title="语言指纹分析",
            message="正在提取多维语言特征并执行统计检验...",
            show_dialog=False,
        )

    def _on_run_progress(self, done: int, total: int) -> None:
        """后台线程的进度回调：只切回主线程刷新内嵌进度条。"""
        if total <= 0:
            return
        frac = min(max(done / total, 0.0), 1.0)
        self.after(0, lambda: self.progress_bar.set(frac))

    def _cancel_run(self) -> None:
        """页面内取消按钮：与进度对话框的取消同一条链路。"""
        if self._runner.is_running():
            self._runner.cancel()

    def _on_cancel(self) -> None:
        """用户取消分析：复位按钮与状态（与成功/失败路径同一套复位逻辑）。"""
        self.run_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.progress_bar.set(0)
        self.app.set_status("语言指纹分析已取消")
        self.results_text.delete("1.0", "end")
        self.results_text.insert("end", "⏹ 分析已取消。\n")

    def _on_result(self, result: linguistic_fingerprint.FingerprintResult,
                   a_len: int, author_b: str, controls: list) -> None:
        from viz import plots as _plots

        self._last = result

        # ── 详细报告 ──
        self.results_text.delete("1.0", "end")
        self.results_text.insert("end", result.summary() + "\n\n")
        self.results_text.insert("end", result.verdict_detail())

        # 补充输入摘要
        b_count = self._count_chars(author_b)
        c_counts = [self._count_chars(c) for c in controls]
        self.results_text.insert(
            "end",
            f"\n\n── 输入摘要 ──\n"
            f"  可疑文本 A: {a_len:,} 字符\n"
            f"  嫌疑作者 B: {b_count:,} 字符\n"
            + "".join(f"  对照作者 C{i+1}: {n:,} 字符\n" for i, n in enumerate(c_counts)),
        )

        # ── 图表 ──
        dark = s.is_dark()
        fig = _plots.make_fingerprint_bar(
            result.similarity_to_b,
            result.similarity_to_controls,
            result.p_value_wilcoxon,
            result.cohens_d,
            result.verdict,
            dark_mode=dark,
        )
        embed_figure(self.chart_holder, fig)

        self.export_btn.configure(state="normal")
        self.app.set_status(f"语言指纹分析完成 — 结论: {result.verdict}")
        self.run_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.progress_bar.set(1)

    def _on_error(self, e: Exception) -> None:
        if isinstance(e, ValueError):
            messagebox.showwarning("输入错误", f"{e}\n\n请检查文本语言和长度是否符合要求。")
            self.app.set_status("输入错误")
        elif isinstance(e, MemoryError):
            messagebox.showerror(
                "内存不足",
                "文本过长导致内存不足。\n"
                "建议：将文本拆分为多个小文件分别分析，或关闭其他程序释放内存。"
            )
            self.app.set_status("内存不足")
        else:
            messagebox.showerror("错误", f"分析失败：{e}\n\n如果问题持续，请检查依赖库是否完整安装。")
            self.app.set_status("分析失败")
        self.run_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.progress_bar.set(0)

    def export(self) -> None:
        if self._last is None:
            return
        from core.export import export_fingerprint_result
        export_fingerprint_result(self._last, self.winfo_toplevel())
