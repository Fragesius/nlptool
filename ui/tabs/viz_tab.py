"""可视化标签页（customtkinter 版）。"""

from __future__ import annotations

from tkinter import messagebox
from typing import Optional

import customtkinter as ctk

from core import analyzer
from ui.async_runner import TaskRunner
from ui import style as s
from ui.tabs.widgets import Card, flat_btn, embed_figure


# --------------------------------------------------------------------------- #
# 可视化
# --------------------------------------------------------------------------- #


class VizTab(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._runner = TaskRunner(self)
        from viz import plots
        self.plots = plots

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── 运行控制：图表选择 ──
        bar_card = Card(self, "📈 图表选择")
        bar_card.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        bar = ctk.CTkFrame(bar_card, fg_color="transparent")
        bar.pack(fill="x", padx=12, pady=(6, 10))
        buttons = [
            ("☁ 词云", "wordcloud"),
            ("📊 词频柱状图", "freq"),
            ("🥧 词性饼图", "pos"),
            ("🌳 依存句法图", "dep"),
            ("📈 情感趋势图", "sent"),
        ]
        for label, kind in buttons:
            flat_btn(bar, text=label, command=lambda k=kind: self.draw(k)).pack(
                side="left", padx=(0, 6)
            )

        # ── 结果展示：画布 ──
        canvas_card = Card(self, "🖼 图表")
        canvas_card.grid(row=1, column=0, sticky="nsew", padx=10, pady=(4, 10))
        self.canvas_holder = ctk.CTkFrame(canvas_card, fg_color="transparent")
        self.canvas_holder.pack(fill="both", expand=True, padx=8, pady=8)

        self._basic: Optional[analyzer.BasicResult] = None
        self._syntax: Optional[analyzer.SyntaxResult] = None
        # 分析结果缓存：相同 (text, lang) 不重复分析（避免连续点击图表按钮时重复跑 spaCy）
        self._cache_key: Optional[tuple] = None
        self._pending_kind: Optional[str] = None

    def _ensure_data(self) -> bool:
        """检查输入文本是否为空；空则提示并返回 False。"""
        text = self.app.get_text()
        if not text.strip():
            messagebox.showinfo("提示", "请先输入待分析文本。")
            return False
        return True  # 需要分析，但交给后台线程执行

    def draw(self, kind: str) -> None:
        if not self._ensure_data():
            return
        if self._runner.is_running():
            return

        self._pending_kind = kind
        text = self.app.get_text()
        lang = self.app.get_lang()
        cache_key = (text, lang)
        if self._cache_key == cache_key and self._basic and self._syntax:
            # 命中缓存，直接绘制
            self._draw_plot(kind)
            return

        self.app.set_status("正在准备可视化数据……")
        self._runner.run(
            self._analyze_for_viz,
            args=(text, lang),
            on_success=lambda pair: self._on_data_ready(pair, kind),
            on_error=self._on_error,
            title="可视化分析",
            message="正在执行基础分析与句法分析，为图表准备数据...",
        )

    def _analyze_for_viz(self, text: str, lang) -> tuple:
        """后台线程执行：返回 (basic, syntax)。"""
        basic = analyzer.analyze_basic(text, lang)
        syntax = analyzer.analyze_syntax(text, lang)
        return basic, syntax

    def _on_data_ready(self, pair: tuple, kind: str) -> None:
        self._basic, self._syntax = pair
        self._cache_key = (self.app.get_text(), self.app.get_lang())
        self._draw_plot(kind)

    def _draw_plot(self, kind: str) -> None:
        self.app.set_status(f"正在生成图表: {kind}……")
        dark = s.is_dark()
        try:
            if kind == "wordcloud":
                fig = self.plots.make_wordcloud(self._basic.freq, dark_mode=dark)
            elif kind == "freq":
                fig = self.plots.make_freq_bar(self._basic.freq, dark_mode=dark)
            elif kind == "pos":
                fig = self.plots.make_pos_pie(self._basic.pos_dist, dark_mode=dark)
            elif kind == "dep":
                fig = self.plots.make_dependency_graph(self._syntax.dependencies, dark_mode=dark)
            elif kind == "sent":
                fig = self.plots.make_sentiment_trend(
                    self.app.get_text(), self.app.get_lang(), dark_mode=dark
                )
            else:
                return
            embed_figure(self.canvas_holder, fig)
            self.app.set_status(f"图表已生成: {kind}")
        except Exception as e:
            messagebox.showerror("错误", f"绘图失败：{e}")
            self.app.set_status(f"绘图失败: {kind}")

    def _on_error(self, e: Exception) -> None:
        messagebox.showerror("错误", f"分析失败：{e}")
        self.app.set_status("分析失败")
