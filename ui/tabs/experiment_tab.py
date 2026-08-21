"""批量实验标签页（customtkinter 版）。"""

from __future__ import annotations

import os
import queue
import tkinter as tk
from tkinter import messagebox, filedialog
from typing import Optional

import customtkinter as ctk

from ui.async_runner import TaskRunner
from ui import style as s
from ui.tabs.widgets import (
    clear_widget, Card, accent_btn, flat_btn, hint_label, add_copy_button,
)


# --------------------------------------------------------------------------- #
# 批量实验（译者风格识别管线 GUI）
# --------------------------------------------------------------------------- #


class ExperimentTab(ctk.CTkFrame):
    """批量分组实验标签页：可选切片 + Burrows' Delta + 语言指纹统计检验。

    左右双栏布局：左侧=结果摘要，右侧=输入设置与运行控制。
    GUI 只负责收集参数、调用 experiments 包的核心函数并展示结果，
    不复制任何实验逻辑。
    """

    # 权重敏感性方案：（显示文字, experiments.weight_sensitivity 的方案键）
    _SENS_SCHEMES = [
        ("全部方案（all，38 变体）", "all"),
        ("随机扰动（random，20 种子）", "random"),
        ("现有权重（default）", "default"),
        ("八维等权（uniform）", "uniform"),
        ("逐维留一（lodo，8 变体）", "lodo"),
        ("单维独立（single，8 变体）", "single"),
    ]

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._runner = TaskRunner(self)
        self._out_dir: Optional[str] = None
        self._report_text = ""
        self._sens_out_dir: Optional[str] = None
        self._sens_report_text = ""

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0, minsize=420)
        self.grid_rowconfigure(0, weight=1)

        # ══ 右栏：输入设置 + 运行控制（可滚动）══
        right = ctk.CTkScrollableFrame(self, fg_color="transparent", width=400)
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 10), pady=10)

        # ══ 左栏：结果展示（可滚动，小窗口也能看到复制按钮）══
        left = ctk.CTkScrollableFrame(self, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 4), pady=10)

        # ══ 输入设置 ══
        input_card = Card(right, "📥 输入设置")
        input_card.pack(fill="x", padx=6, pady=(4, 4))

        # ── 语料目录 ──
        row1 = ctk.CTkFrame(input_card, fg_color="transparent")
        row1.pack(fill="x", padx=12, pady=(8, 0))
        ctk.CTkLabel(row1, text="语料目录：", font=s.font("body")).pack(side="left")
        self.input_var = tk.StringVar()
        ctk.CTkEntry(row1, textvariable=self.input_var,
                     font=s.font("body")).pack(
            side="left", fill="x", expand=True, padx=(4, 4))
        flat_btn(row1, text="📂 浏览…", width=90,
                 command=self._pick_input).pack(side="left")

        hint_label(
            input_card,
            "目录需按 一级子文件夹=组别（译者） 组织，每个组文件夹内放该组的 .txt 样本",
            pady=(2, 4),
        )

        # ── 输出目录 ──
        row2 = ctk.CTkFrame(input_card, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(row2, text="输出目录：", font=s.font("body")).pack(side="left")
        self.output_var = tk.StringVar()
        ctk.CTkEntry(row2, textvariable=self.output_var,
                     font=s.font("body")).pack(
            side="left", fill="x", expand=True, padx=(4, 4))
        flat_btn(row2, text="📂 浏览…", width=90,
                 command=self._pick_output).pack(side="left")

        hint_label(
            input_card,
            "留空则默认为 语料目录/experiment_output",
            pady=(2, 4),
        )

        # ── 选项行：切片词数 + 运行模式 ──
        opts = ctk.CTkFrame(input_card, fg_color="transparent")
        opts.pack(fill="x", padx=12, pady=(2, 4))
        ctk.CTkLabel(opts, text="切片词数：", font=s.font("body")).pack(side="left")
        self.chunk_var = tk.StringVar(value="2000")
        ctk.CTkEntry(opts, textvariable=self.chunk_var, width=80,
                     font=s.font("body")).pack(side="left", padx=(4, 12))

        self.clean_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            opts, text="运行前清空输出目录",
            variable=self.clean_var,
            font=s.font("body"),
        ).pack(side="left")

        mode_row = ctk.CTkFrame(input_card, fg_color="transparent")
        mode_row.pack(fill="x", padx=12, pady=(0, 10))
        self.mode_var = tk.StringVar(value="slice")
        ctk.CTkRadioButton(
            mode_row, text="切片后实验（长文本）",
            variable=self.mode_var, value="slice",
            font=s.font("body"),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkRadioButton(
            mode_row, text="直接实验（已切好/短文本）",
            variable=self.mode_var, value="direct",
            font=s.font("body"),
        ).pack(side="left")

        # ══ 运行控制 ══
        ctrl_card = Card(right, "▶ 运行控制")
        ctrl_card.pack(fill="x", padx=6, pady=4)

        ctrl = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        ctrl.pack(fill="x", padx=12, pady=(6, 4))
        self.run_btn = accent_btn(ctrl, text="▶ 开始实验", command=self.run)
        self.run_btn.pack(side="left")
        self.open_btn = flat_btn(ctrl, text="📂 打开输出文件夹",
                                 command=self._open_output, state="disabled")
        self.open_btn.pack(side="left", padx=(8, 0))
        self.cancel_btn = flat_btn(ctrl, text="⏹ 取消", command=self._cancel_run,
                                   state="disabled")
        self.cancel_btn.pack(side="left", padx=(8, 0))

        # ── 确定性进度条 + 阶段文字 ──
        prog = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        prog.pack(fill="x", padx=12, pady=(0, 10))
        self.stage_var = tk.StringVar(value="")
        ctk.CTkLabel(
            prog, textvariable=self.stage_var,
            font=s.font("caption"), text_color=s.MUTED,
        ).pack(side="left")
        self.progress_bar = ctk.CTkProgressBar(prog, width=280)
        self.progress_bar.pack(side="right")
        self.progress_bar.set(0)
        self._progress_queue: "queue.Queue[tuple]" = queue.Queue()

        # ══ 权重敏感性（v2.3.0）══
        sens_card = Card(right, "⚖ 权重敏感性")
        sens_card.pack(fill="x", padx=6, pady=4)

        hint_label(
            sens_card,
            "检验结论是否依赖复合指纹的启发式权重：按 权重变体 × 尺度 重算指纹指标",
            pady=(2, 4),
        )

        # ── 语料目录（原始语料，自动切片）──
        crow = ctk.CTkFrame(sens_card, fg_color="transparent")
        crow.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(crow, text="语料目录：",
                     font=s.font("body")).pack(side="left")
        self.sens_input_var = tk.StringVar()
        ctk.CTkEntry(crow, textvariable=self.sens_input_var,
                     font=s.font("body")).pack(
            side="left", fill="x", expand=True, padx=(4, 4))
        flat_btn(crow, text="📂 浏览…", width=90,
                 command=self._pick_sens_input).pack(side="left")

        hint_label(
            sens_card,
            "原始语料按 一级子文件夹=组别（译者） 组织；按勾选规模自动切片后分析",
            pady=(2, 4),
        )

        # ── 切片规模：1k/2k/4k 勾选 + 自定义词数 ──
        scale_row = ctk.CTkFrame(sens_card, fg_color="transparent")
        scale_row.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(scale_row, text="切片规模：",
                     font=s.font("body")).pack(side="left")
        self.sens_scale_checks = {}
        for label, size in (("1k", 1000), ("2k", 2000), ("4k", 4000)):
            var = tk.BooleanVar(value=True)
            self.sens_scale_checks[size] = var
            ctk.CTkCheckBox(scale_row, text=label, variable=var,
                            font=s.font("body")).pack(side="left",
                                                      padx=(4, 4))

        # ── 自定义规模（单独一行，窄栏不被挤出）──
        custom_row = ctk.CTkFrame(sens_card, fg_color="transparent")
        custom_row.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(custom_row, text="自定义规模：",
                     font=s.font("body")).pack(side="left")
        self.sens_custom_var = tk.StringVar()
        ctk.CTkEntry(custom_row, textvariable=self.sens_custom_var,
                     width=90, font=s.font("body")).pack(side="left",
                                                         padx=(4, 2))
        ctk.CTkLabel(custom_row, text="词（留空则不用）",
                     font=s.font("body")).pack(side="left", padx=(2, 0))

        # ── 权重方案 ──
        scheme_row = ctk.CTkFrame(sens_card, fg_color="transparent")
        scheme_row.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(scheme_row, text="权重方案：",
                     font=s.font("body")).pack(side="left")
        self.sens_scheme_var = tk.StringVar(value=self._SENS_SCHEMES[0][0])
        ctk.CTkOptionMenu(
            scheme_row, variable=self.sens_scheme_var,
            values=[label for label, _ in self._SENS_SCHEMES],
            width=220, font=s.font("body"),
        ).pack(side="left", padx=(4, 0))

        # ── 输出目录 ──
        orow = ctk.CTkFrame(sens_card, fg_color="transparent")
        orow.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(orow, text="输出目录：", font=s.font("body")).pack(side="left")
        self.sens_output_var = tk.StringVar()
        ctk.CTkEntry(orow, textvariable=self.sens_output_var,
                     font=s.font("body")).pack(
            side="left", fill="x", expand=True, padx=(4, 4))
        flat_btn(orow, text="📂 浏览…", width=90,
                 command=self._pick_sens_output).pack(side="left")

        hint_label(
            sens_card,
            "留空则默认为 语料目录/weight_sensitivity（切片存于其下 sliced_* 子目录）",
            pady=(2, 4),
        )

        # ── 追加到报告（可选）──
        rrow = ctk.CTkFrame(sens_card, fg_color="transparent")
        rrow.pack(fill="x", padx=12, pady=2)
        ctk.CTkLabel(rrow, text="追加到报告：",
                     font=s.font("body")).pack(side="left")
        self.sens_report_var = tk.StringVar()
        ctk.CTkEntry(rrow, textvariable=self.sens_report_var,
                     font=s.font("body")).pack(
            side="left", fill="x", expand=True, padx=(4, 4))
        flat_btn(rrow, text="📂 浏览…", width=90,
                 command=self._pick_sens_report).pack(side="left")

        hint_label(
            sens_card,
            "可选：在既有 report.md 末尾纯追加一节「Weight sensitivity」，不改动既有内容",
            pady=(2, 4),
        )

        srun = ctk.CTkFrame(sens_card, fg_color="transparent")
        srun.pack(fill="x", padx=12, pady=(4, 10))
        self.sens_run_btn = accent_btn(
            srun, text="⚖ 运行敏感性分析", command=self.run_sensitivity)
        self.sens_run_btn.pack(side="left")
        self.sens_open_btn = flat_btn(
            srun, text="📂 打开输出文件夹",
            command=self._open_sens_output, state="disabled")
        self.sens_open_btn.pack(side="left", padx=(8, 0))

        # ══ 结果展示：摘要网格 ══
        result_card = Card(left, "📋 实验结果摘要")
        result_card.pack(fill="both", expand=True)

        self.metrics_grid = ctk.CTkFrame(result_card, fg_color="transparent")
        self.metrics_grid.pack(fill="x", padx=12, pady=(6, 4))
        self.metrics_grid.grid_columnconfigure(1, weight=1)

        self._placeholder_label = ctk.CTkLabel(
            self.metrics_grid,
            text=(
                "请选择语料目录后点击「▶ 开始实验」。\n\n"
                "流程：\n"
                "  1. （可选）按切片词数把长文本切成定长切片\n"
                "  2. 对全部样本计算 Burrows' Delta 距离矩阵并聚类\n"
                "  3. 计算语言指纹两两相似度，做 Wilcoxon / 置换检验 / Cohen's d\n"
                "  4. 输出 delta_matrix.csv、dendrogram.png、fingerprint_pairs.csv、report.md"
            ),
            font=s.font("body"), text_color=s.MUTED,
            anchor="w", justify="left",
        )
        self._placeholder_label.grid(row=0, column=0, columnspan=2,
                                     sticky="w", pady=4)

        self.conclusion_label = ctk.CTkLabel(
            result_card, text="",
            font=s.font("body", bold=True),
            anchor="w", justify="left", wraplength=560,
        )
        self.conclusion_label.pack(fill="x", padx=12, pady=(4, 2))

        self.out_dir_label = ctk.CTkLabel(
            result_card, text="",
            font=s.font("footnote"), text_color=s.MUTED,
            anchor="w", justify="left", wraplength=560,
        )
        self.out_dir_label.pack(fill="x", padx=12, pady=(0, 4))
        add_copy_button(result_card, lambda: self._report_text,
                        label="📋 复制摘要")

        # ══ 权重敏感性结果 ══
        sens_result_card = Card(left, "⚖ 权重敏感性结果")
        sens_result_card.pack(fill="both", expand=True, pady=(8, 0))

        self.sens_metrics_grid = ctk.CTkFrame(
            sens_result_card, fg_color="transparent")
        self.sens_metrics_grid.pack(fill="x", padx=12, pady=(6, 4))
        self.sens_metrics_grid.grid_columnconfigure(1, weight=1)

        self._sens_placeholder = ctk.CTkLabel(
            self.sens_metrics_grid,
            text=(
                "尚未运行权重敏感性分析。\n\n"
                "在右侧选择原始语料目录、勾选切片规模后点击「⚖ 运行敏感性分析」，\n"
                "将自动切片并输出 weight_sensitivity.csv（长表：变体 × 尺度），\n"
                "可选在既有 report.md 末尾追加一节。"
            ),
            font=s.font("body"), text_color=s.MUTED,
            anchor="w", justify="left",
        )
        self._sens_placeholder.grid(row=0, column=0, columnspan=2,
                                    sticky="w", pady=4)

        self.sens_conclusion_label = ctk.CTkLabel(
            sens_result_card, text="",
            font=s.font("body", bold=True),
            anchor="w", justify="left", wraplength=560,
        )
        self.sens_conclusion_label.pack(fill="x", padx=12, pady=(4, 2))

        self.sens_out_label = ctk.CTkLabel(
            sens_result_card, text="",
            font=s.font("footnote"), text_color=s.MUTED,
            anchor="w", justify="left", wraplength=560,
        )
        self.sens_out_label.pack(fill="x", padx=12, pady=(0, 4))
        add_copy_button(sens_result_card, lambda: self._sens_report_text,
                        label="📋 复制摘要")

    # ── 指标网格 ──
    def _metric(self, index: int, name: str, value: str,
                color=None, target=None) -> None:
        """在单列网格中添加一行指标（显著=绿、不显著=灰）。

        ``target`` 缺省为实验结果网格，敏感性结果传入自己的网格。
        """
        grid = target if target is not None else self.metrics_grid
        ctk.CTkLabel(
            grid, text=name,
            font=s.font("footnote"), text_color=s.MUTED,
            anchor="e", width=180,
        ).grid(row=index, column=0, sticky="e", padx=(4, 8), pady=2)
        ctk.CTkLabel(
            grid, text=value,
            font=s.font("body", bold=True, mono=True),
            text_color=color if color is not None else s.TEXT,
            anchor="w", justify="left", wraplength=400,
        ).grid(row=index, column=1, sticky="w", padx=(0, 8), pady=2)

    @staticmethod
    def _sig_color(p: float) -> tuple:
        """显著性语义色：显著=绿、不显著=灰。"""
        return s.SUCCESS if p < 0.05 else s.MUTED

    # ── 目录选择 ──
    def _pick_input(self) -> None:
        path = filedialog.askdirectory(title="选择语料目录")
        if not path:
            return
        self.input_var.set(path)
        # 输出目录为空时自动填默认值
        if not self.output_var.get().strip():
            self.output_var.set(os.path.join(path, "experiment_output"))

    def _pick_output(self) -> None:
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.output_var.set(path)

    # ── 运行 ──
    def run(self) -> None:
        input_dir = self.input_var.get().strip()
        if not input_dir:
            messagebox.showinfo("提示", "请先选择语料目录。")
            return
        if not os.path.isdir(input_dir):
            messagebox.showerror("错误", f"语料目录不存在：{input_dir}")
            return

        out_dir = self.output_var.get().strip()
        if not out_dir:
            out_dir = os.path.join(input_dir, "experiment_output")
            self.output_var.set(out_dir)

        try:
            chunk_size = int(self.chunk_var.get().strip())
            if chunk_size <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("错误", "切片词数必须是正整数。")
            return

        if self._runner.is_running():
            return

        mode = self.mode_var.get()
        clean = self.clean_var.get()
        self.run_btn.configure(state="disabled")
        self.sens_run_btn.configure(state="disabled")
        self.open_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.stage_var.set("准备中…")
        self.progress_bar.set(0)
        self.app.set_status("正在运行批量实验……")
        self._runner.run(
            self._do_experiment,
            args=(input_dir, out_dir, chunk_size, mode, clean),
            kwargs={"progress_callback": self._enqueue_progress},
            on_success=self._on_result,
            on_error=self._on_error,
            on_cancel=self._on_cancelled,
            title="批量实验",
            message="正在执行切片与分组实验（Delta 聚类 + 指纹检验），请稍候...",
            show_dialog=False,
        )
        self._drain_progress()

    def _cancel_run(self) -> None:
        """页面内取消按钮：与进度对话框的取消同一条链路。"""
        if self._runner.is_running():
            self._runner.cancel()

    def _on_cancelled(self) -> None:
        """任务被取消：复位运行控制与进度显示。"""
        self.stage_var.set("已取消")
        self.progress_bar.set(0)
        self.cancel_btn.configure(state="disabled")
        self.run_btn.configure(state="normal")
        self.sens_run_btn.configure(state="normal")
        self.app.set_status("已取消")

    # ── 进度回调（后台线程）与主线程刷新 ──
    def _enqueue_progress(self, current: int, total: int, stage: str) -> None:
        """后台线程的进度回调：只入队，不碰 UI。

        兼作协作式取消检查点：管线各处（切片/实验/权重敏感性）的进度
        回调均为裸调用、无 try 包裹，取消时在此抛 TaskCancelled 可立即
        中断整个后台任务。
        """
        self._runner.check_cancelled()
        self._progress_queue.put((current, total, stage))

    def _drain_progress(self) -> None:
        """主线程轮询进度队列，刷新进度条与阶段文字。"""
        try:
            while True:
                current, total, stage = self._progress_queue.get_nowait()
                self.stage_var.set(f"{stage} {current:,}/{total:,}")
                self.progress_bar.set(current / max(total, 1))
        except queue.Empty:
            pass
        if self._runner.is_running():
            self.after(100, self._drain_progress)

    @staticmethod
    def _do_experiment(input_dir: str, out_dir: str, chunk_size: int,
                       mode: str, clean: bool,
                       progress_callback=None) -> tuple:
        """后台线程执行：可选切片 + 分组实验，返回 (stats, out_dir)。

        只调用 experiments 包的核心函数，不复制实验逻辑。
        """
        from pathlib import Path

        # plot_dendrogram 走 pyplot：GUI 下默认是 TkAgg，
        # 在非主线程建图会崩溃，临时切到无界面的 Agg 后端。
        import matplotlib
        import matplotlib.pyplot as plt

        prev_backend = matplotlib.get_backend()
        if prev_backend.lower() != "agg":
            plt.switch_backend("Agg")
        try:
            from experiments.slice_corpus import slice_corpus
            from experiments.run_experiment import run as run_experiment

            exp_input = Path(input_dir)
            if mode == "slice":
                sliced_dir = Path(out_dir) / "sliced_corpus"
                written = slice_corpus(Path(input_dir), sliced_dir,
                                       chunk_size, clean=clean,
                                       progress_callback=progress_callback)
                if not written:
                    raise ValueError(
                        "切片结果为空：所有文本都短于 0.5 × 切片词数，"
                        "请减小切片词数，或改用「直接实验」。"
                    )
                exp_input = sliced_dir

            stats = run_experiment(exp_input, Path(out_dir),
                                   progress_callback=progress_callback)
        finally:
            if prev_backend.lower() != "agg":
                plt.switch_backend(prev_backend)
        return stats, out_dir

    def _on_result(self, payload: tuple) -> None:
        import math

        stats, out_dir = payload
        self._out_dir = out_dir

        ratio = stats["delta_ratio"]
        ratio_str = f"{ratio:.2f}" if math.isfinite(ratio) else "inf（组内为 0）"
        groups_str = "，".join(
            f"{g}: {n} 样本" for g, n in stats["groups"].items())

        nn_acc = stats["nn_accuracy"]
        nn_base = stats["nn_baseline"]
        sc_p = stats["sc_p_value"]
        p_wil = stats["p_wilcoxon"]
        p_perm = stats["p_permutation"]

        def _sig_text(p: float) -> str:
            return f"{p:.4f}（{'显著' if p < 0.05 else '不显著'}）"

        # 重建指标网格
        clear_widget(self.metrics_grid)
        metrics = [
            ("样本数", f"{stats['n_samples']} 个 / {len(stats['groups'])} 组", None),
            ("分组构成", groups_str, None),
            ("组内平均 Delta", f"{stats['within_delta_mean']:.4f}", None),
            ("组间平均 Delta", f"{stats['cross_delta_mean']:.4f}", None),
            ("差值（组间 − 组内）", f"{stats['delta_diff']:.4f}", None),
            ("比值（组间 / 组内）", ratio_str,
             s.SUCCESS if math.isfinite(ratio) and ratio > 1 else s.MUTED),
            ("1-NN 留一法准确率",
             f"{nn_acc:.4f}（随机基线 {nn_base:.4f}）",
             s.SUCCESS if nn_acc > nn_base else s.MUTED),
            ("信号竞争（原文 : 译者）",
             f"{stats['sc_wins_original']} : {stats['sc_wins_translator']}", None),
            ("信号竞争符号检验 p", _sig_text(sc_p), self._sig_color(sc_p)),
            ("同译者对平均相似度", f"{stats['same_sim_mean']:.4f}", None),
            ("跨译者对平均相似度", f"{stats['cross_sim_mean']:.4f}", None),
            ("Wilcoxon 符号秩检验 p", _sig_text(p_wil), self._sig_color(p_wil)),
            ("置换检验 p", _sig_text(p_perm), self._sig_color(p_perm)),
            ("Cohen's d", f"{stats['cohens_d']:.3f}", None),
        ]
        for i, (name, value, color) in enumerate(metrics):
            self._metric(i, name, value, color)

        # 纯文本摘要（供「复制摘要」按钮分享）
        self._report_text = "\n".join(
            ["批量实验结果摘要", ""]
            + [f"{name}：{value}" for name, value, _ in metrics]
            + ["", f"【结论】{stats['conclusion']}",
               f"输出目录：{out_dir}"]
        )

        self.conclusion_label.configure(text=f"【结论】{stats['conclusion']}")
        self.out_dir_label.configure(text=f"完整报告与图表见输出目录：{out_dir}")

        self.stage_var.set("完成")
        self.progress_bar.set(1)
        self.open_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.run_btn.configure(state="normal")
        self.sens_run_btn.configure(state="normal")
        self.app.set_status(
            f"批量实验完成 — 组间/组内 Delta 比值 {ratio_str}")

    def _on_error(self, e: Exception) -> None:
        messagebox.showerror(
            "实验失败",
            f"{e}\n\n请检查：语料目录下是否至少有 2 个组子文件夹，"
            f"且每组至少 2 个 .txt 样本。",
        )
        self.stage_var.set("失败")
        self.progress_bar.set(0)
        self.cancel_btn.configure(state="disabled")
        self.run_btn.configure(state="normal")
        self.sens_run_btn.configure(state="normal")
        self.app.set_status("批量实验失败")

    def _open_output(self) -> None:
        if not self._out_dir:
            return
        self._open_folder(self._out_dir)

    # ── 权重敏感性（v2.3.0）──
    def _pick_sens_input(self) -> None:
        path = filedialog.askdirectory(title="选择语料目录（原始文本）")
        if not path:
            return
        self.sens_input_var.set(path)
        # 输出目录为空时自动填默认值
        if not self.sens_output_var.get().strip():
            self.sens_output_var.set(
                os.path.join(path, "weight_sensitivity"))

    def _pick_sens_output(self) -> None:
        path = filedialog.askdirectory(title="选择敏感性分析输出目录")
        if path:
            self.sens_output_var.set(path)

    def _pick_sens_report(self) -> None:
        path = filedialog.askopenfilename(
            title="选择要追加的 report.md",
            filetypes=[("Markdown 报告", "*.md")])
        if path:
            self.sens_report_var.set(path)

    def run_sensitivity(self) -> None:
        """收集语料目录与切片规模，后台自动切片并运行权重敏感性分析。"""
        input_dir = self.sens_input_var.get().strip()
        if not input_dir:
            messagebox.showinfo("提示", "请先选择语料目录。")
            return
        if not os.path.isdir(input_dir):
            messagebox.showerror("错误", f"语料目录不存在：{input_dir}")
            return

        sizes = [size for size, var in self.sens_scale_checks.items()
                 if var.get()]
        custom = self.sens_custom_var.get().strip()
        if custom:
            try:
                csize = int(custom)
                if csize <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    "错误", "自定义切片规模必须是正整数（词数）。")
                return
            if csize not in sizes:
                sizes.append(csize)
        if not sizes:
            messagebox.showinfo(
                "提示", "请至少勾选一个切片规模，或填写自定义规模。")
            return

        scheme = dict(self._SENS_SCHEMES)[self.sens_scheme_var.get()]

        out_dir = self.sens_output_var.get().strip()
        if not out_dir:
            out_dir = os.path.join(input_dir, "weight_sensitivity")
            self.sens_output_var.set(out_dir)

        report = self.sens_report_var.get().strip()
        if report and not os.path.isfile(report):
            messagebox.showerror("错误", f"报告文件不存在：{report}")
            return

        if self._runner.is_running():
            return

        self.run_btn.configure(state="disabled")
        self.sens_run_btn.configure(state="disabled")
        self.sens_open_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.stage_var.set("准备中…")
        self.progress_bar.set(0)
        self.app.set_status("正在自动切片并运行权重敏感性分析……")
        self._runner.run(
            self._do_sensitivity,
            args=(input_dir, sizes, scheme, out_dir, report or None),
            kwargs={"progress_callback": self._enqueue_progress},
            on_success=self._on_sens_result,
            on_error=self._on_sens_error,
            on_cancel=self._on_cancelled,
            title="权重敏感性",
            message="正在自动切片并按 权重变体 × 尺度 重算指纹指标，请稍候...",
            show_dialog=False,
        )
        self._drain_progress()

    @staticmethod
    def _do_sensitivity(input_dir: str, sizes: list, scheme: str,
                        out_dir: str, report: Optional[str],
                        progress_callback=None) -> tuple:
        """后台线程执行：按勾选规模自动切片 + 权重敏感性分析。

        返回 (rows, out_dir, scheme)。只调用 experiments 包的核心函数
        （slice_corpus / weight_sensitivity.run_sensitivity），
        不复制实验逻辑。
        """
        from pathlib import Path

        # 与 _do_experiment 同理：惰性导入链会触及 matplotlib，
        # 在非主线程临时切到无界面的 Agg 后端。
        import matplotlib
        import matplotlib.pyplot as plt

        prev_backend = matplotlib.get_backend()
        if prev_backend.lower() != "agg":
            plt.switch_backend("Agg")
        try:
            from experiments.slice_corpus import slice_corpus
            from experiments.weight_sensitivity import (
                run_sensitivity as _run_sensitivity,
            )

            # 自动切片：每个规模切到 输出目录/sliced_{size}（清空旧切片）
            scale_inputs = {}
            for size in sizes:
                label = f"{size / 1000:g}k"
                sliced_dir = Path(out_dir) / f"sliced_{size}"
                written = slice_corpus(Path(input_dir), sliced_dir, size,
                                       clean=True,
                                       progress_callback=progress_callback)
                if not written:
                    raise ValueError(
                        f"{label} 尺度切片为空：所有文本都短于 "
                        f"0.5 × {size} 词，请取消该尺度或减小切片规模。")
                scale_inputs[label] = sliced_dir

            rows = _run_sensitivity(
                scale_inputs, scheme=scheme, out_dir=Path(out_dir),
                report_path=Path(report) if report else None,
                progress_callback=progress_callback,
            )
        finally:
            if prev_backend.lower() != "agg":
                plt.switch_backend(prev_backend)
        return rows, out_dir, scheme

    def _on_sens_result(self, payload: tuple) -> None:
        rows, out_dir, scheme = payload
        self._sens_out_dir = out_dir

        scales: list = []
        for r in rows:
            if r["scale"] not in scales:
                scales.append(r["scale"])
        n_variants = len({r["variant"] for r in rows})

        clear_widget(self.sens_metrics_grid)
        metrics = [("方案 / 规模",
                    f"{scheme} — {n_variants} 变体 × {len(scales)} 尺度", None)]
        for scale in scales:
            srows = [r for r in rows if r["scale"] == scale]
            ds = [r["d"] for r in srows]
            wins = [r["competition_wins"] for r in srows]
            pairs = max(r["competition_pairs"] for r in srows)
            accs = [r["knn_acc"] for r in srows]
            base = srows[0]["knn_baseline"]
            metrics.append((
                f"Cohen's d 范围（{scale}）",
                f"{min(ds):.3f} ~ {max(ds):.3f}",
                s.SUCCESS if min(ds) > 0 else s.MUTED))
            metrics.append((
                f"信号竞争原文胜（{scale}）",
                f"{min(wins)} ~ {max(wins)} / {pairs}",
                s.SUCCESS if pairs and min(wins) > pairs / 2 else s.MUTED))
            metrics.append((
                f"1-NN 准确率（{scale}）",
                f"{min(accs):.4f} ~ {max(accs):.4f}（基线 {base:.4f}）",
                s.SUCCESS if min(accs) > base else s.MUTED))
        for i, (name, value, color) in enumerate(metrics):
            self._metric(i, name, value, color, target=self.sens_metrics_grid)

        # 一句话结论：所有变体 × 尺度下 d>0 且原文信号获胜过半才算稳定
        d_min = min(r["d"] for r in rows)
        win_min = min(r["competition_wins"] for r in rows)
        pairs_max = max(r["competition_pairs"] for r in rows)
        stable = d_min > 0 and (pairs_max == 0 or win_min > pairs_max / 2)
        if stable:
            conclusion = (
                f"全部 {n_variants} 个变体 × {len(scales)} 个尺度下 "
                f"Cohen's d 均为正、原文信号获胜过半："
                f"结论不依赖启发式权重。")
        else:
            conclusion = (
                "部分变体/尺度下结论有变化，"
                "请查看 weight_sensitivity.csv 定位受影响的变体。")
        conclusion += (
            "（头条 Delta 结果——距离矩阵、信号竞争、树状图——"
            "不读取权重配置，与权重天然解耦。）")

        self._sens_report_text = "\n".join(
            ["权重敏感性结果摘要", ""]
            + [f"{name}：{value}" for name, value, _ in metrics]
            + ["", f"【结论】{conclusion}", f"输出目录：{out_dir}"]
        )

        self.sens_conclusion_label.configure(text=f"【结论】{conclusion}")
        self.sens_out_label.configure(
            text=f"长表见输出目录：{out_dir}/weight_sensitivity.csv")

        self.stage_var.set("完成")
        self.progress_bar.set(1)
        self.sens_open_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.run_btn.configure(state="normal")
        self.sens_run_btn.configure(state="normal")
        self.app.set_status(
            f"权重敏感性分析完成 — {n_variants} 变体 × {len(scales)} 尺度")

    def _on_sens_error(self, e: Exception) -> None:
        messagebox.showerror(
            "敏感性分析失败",
            f"{e}\n\n请检查：语料目录下是否至少有 2 个组子文件夹，"
            f"且每组文本足够长（切片后每组至少 2 个样本）。",
        )
        self.stage_var.set("失败")
        self.progress_bar.set(0)
        self.cancel_btn.configure(state="disabled")
        self.run_btn.configure(state="normal")
        self.sens_run_btn.configure(state="normal")
        self.app.set_status("权重敏感性分析失败")

    def _open_sens_output(self) -> None:
        if not self._sens_out_dir:
            return
        self._open_folder(self._sens_out_dir)

    @staticmethod
    def _open_folder(folder: str) -> None:
        import subprocess
        import sys

        path = os.path.normpath(folder)
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开输出文件夹：{e}")
