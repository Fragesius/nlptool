"""各功能标签页（customtkinter 版）。

布局统一为「输入设置 / 运行控制 / 结果展示」三段式卡片分区，
强调色与配色常量集中在 ui.style。
"""

from __future__ import annotations

import os
import queue
import re
import tkinter as tk
from tkinter import messagebox, filedialog
from typing import Optional

import customtkinter as ctk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from core import (
    analyzer, comparison, api_backend, history,
    linguistic_fingerprint, batch, file_io,
)
from ui.async_runner import TaskRunner
from ui import style as s
from ui.style import is_compact_mode, get_screen_size


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


# --------------------------------------------------------------------------- #
# 句法 / 语义
# --------------------------------------------------------------------------- #


class SyntaxTab(ctk.CTkFrame):
    _SUB_TITLES = {
        "ner": "🏷 命名实体",
        "kw": "🔑 关键词",
        "dep": "🌳 依存句法",
        "sent": "💬 情感分析",
        "api": "🤖 AI 高级",
    }

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._runner = TaskRunner(self)
        self._last: Optional[analyzer.SyntaxResult] = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── 运行控制 ──
        ctrl_card = Card(self, "▶ 运行控制")
        ctrl_card.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        ctrl = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        ctrl.pack(fill="x", padx=12, pady=(6, 10))
        accent_btn(ctrl, text="▶ 运行句法/语义分析",
                   command=self.run_local).pack(side="left")
        flat_btn(ctrl, text="🤖 AI 高级分析",
                 command=self.run_api).pack(side="left", padx=8)
        self.export_btn = flat_btn(ctrl, text="📤 导出结果", command=self.export,
                                   state="disabled")
        self.export_btn.pack(side="left", padx=(8, 0))

        # ── 结果展示：子标签页 ──
        nb = ctk.CTkTabview(
            self,
            fg_color=s.CARD, corner_radius=10,
            border_width=1, border_color=s.BORDER,
            segmented_button_fg_color=s.BG,
            segmented_button_selected_color=s.ACCENT,
            segmented_button_selected_hover_color=s.ACCENT_HOVER,
            segmented_button_unselected_color=s.BG,
            segmented_button_unselected_hover_color=s.BUTTON_NEUTRAL_HOVER,
            anchor="w",
        )
        nb.grid(row=1, column=0, sticky="nsew", padx=10, pady=4)
        self._sub_nb = nb

        for key in ("ner", "kw", "dep", "sent", "api"):
            nb.add(self._SUB_TITLES[key])

        self.ner_tab = nb.tab(self._SUB_TITLES["ner"])
        self.kw_tab = nb.tab(self._SUB_TITLES["kw"])
        self.dep_tab = nb.tab(self._SUB_TITLES["dep"])
        self.sent_tab = nb.tab(self._SUB_TITLES["sent"])
        self.api_tab = nb.tab(self._SUB_TITLES["api"])

        self.ner_text = make_labeled_text(self.ner_tab, "命名实体  —  实体 / 类型")
        self.kw_text = make_labeled_text(self.kw_tab, "关键词  —  词语 / 权重")

        # ── 依存句法：文字列表（可视化请在「可视化」标签查看树图）──
        self.dep_text = make_labeled_text(
            self.dep_tab,
            "依存关系  —  词元(词性)  ──依存──▶  head(head词性)"
        )
        self._dep_sentences: list[list[dict]] = []

        self.sent_text = make_labeled_text(self.sent_tab, "情感得分  —  -1 负向  ~  1 正向")
        self.api_text = make_labeled_text(self.api_tab, "AI 返回结果")

        taskbar = ctk.CTkFrame(self.api_tab, fg_color="transparent")
        taskbar.pack(fill="x", padx=12, pady=(4, 2))
        ctk.CTkLabel(taskbar, text="分析任务：", font=s.font("body")).pack(side="left")
        self.api_task = tk.StringVar(value="综合语言学分析")
        ctk.CTkOptionMenu(
            taskbar,
            variable=self.api_task,
            values=[
                "综合语言学分析",
                "句法结构分析",
                "文体风格分析",
                "翻译质量评估",
                "修辞手法分析",
            ],
            width=180, font=s.font("body"),
        ).pack(side="left", padx=6)

    def run_local(self) -> None:
        text = self.app.get_text()
        if not text.strip():
            messagebox.showinfo("提示", "请先输入待分析文本。")
            return
        if self._runner.is_running():
            return

        lang = self.app.get_lang()
        self.app.set_status("正在执行句法/语义分析……")
        self._runner.run(
            analyzer.analyze_syntax,
            args=(text, lang),
            on_success=lambda res: self._on_local_result(res, text, lang),
            on_error=self._on_error,
            title="句法/语义分析",
            message="正在执行命名实体识别、关键词提取、依存句法分析与情感分析...",
        )

    def _on_local_result(self, res: analyzer.SyntaxResult, text: str, lang) -> None:
        self._last = res

        # NER
        self.ner_text.delete("1.0", "end")
        if not res.ner:
            self.ner_text.insert("end", _ner_status_msg(lang))
        else:
            for e in res.ner:
                self.ner_text.insert("end", f"{e['text']:<24s}{e['label']}\n")

        # 关键词
        self.kw_text.delete("1.0", "end")
        for w, weight in res.keywords:
            self.kw_text.insert("end", f"{w:<24s}{weight:.4f}\n")

        # 依存句法 — 文字列表
        self._dep_sentences.clear()
        self.dep_text.delete("1.0", "end")
        sentences: list[list[dict]] = []
        if res.dependencies:
            # 按 sent_id 分组
            cur_sid, cur = None, []
            for d in res.dependencies:
                sid = d.get("sent_id", 0)
                if sid != cur_sid:
                    if cur:
                        sentences.append(cur)
                    cur, cur_sid = [d], sid
                else:
                    cur.append(d)
            if cur:
                sentences.append(cur)
            self._dep_sentences = sentences

            for si, sent_deps in enumerate(sentences):
                self.dep_text.insert("end", f"\n【句子 S{si + 1}】\n")
                for d in sent_deps:
                    dep = d.get("dep", "")
                    if dep == "ROOT":
                        self.dep_text.insert(
                            "end",
                            f"  {d['text']:<12s}({d.get('pos', ''):<6s})  ──ROOT──▶  [根节点]\n",
                        )
                    else:
                        self.dep_text.insert(
                            "end",
                            f"  {d['text']:<12s}({d.get('pos', ''):<6s})  ──{dep:<12s}──▶  "
                            f"{d.get('head_text', ''):<12s}({d.get('head_pos', '')})\n",
                        )
        else:
            self.dep_text.insert("end", _dep_status_msg(lang))

        # 情感
        self.sent_text.delete("1.0", "end")
        sent = res.sentiment
        emoji = {"正向": "😊", "中性": "😐", "负向": "😞"}.get(sent["label"], "")
        self.sent_text.insert("end", f"情感倾向：{sent['label']} {emoji}\n")
        self.sent_text.insert("end", f"得分：{sent['score']:.4f}（-1 负向 ~ 1 正向）\n")
        self.sent_text.insert("end", f"原始值：{sent['raw']}\n")

        self.export_btn.configure(state="normal")

        # 保存历史
        try:
            lang_name = analyzer.detect_language(text)
            lang_label = {"zh": "中文", "en": "英文", "mixed": "中英混合"}.get(lang_name, lang_name)
            entry = history.build_entry(
                text=text,
                lang=lang_label,
                ner_preview=", ".join(
                    f"{e['text']}({e['label']})" for e in res.ner[:10]
                ),
                keywords_preview=", ".join(
                    f"{w}({weight:.2f})" for w, weight in res.keywords[:10]
                ),
                sentiment_label=sent["label"],
                sentiment_score=sent["score"],
            )
            history.add_entry(entry)
        except Exception:
            pass

        self.app.set_status(
            f"句法分析完成 — {len(res.ner)} 实体, {len(res.keywords)} 关键词"
        )

        # 通知主窗口标注句子
        try:
            self.app.annotate_sentences(len(sentences))
        except Exception:
            pass

    def _on_error(self, e: Exception) -> None:
        messagebox.showerror("错误", f"分析失败：{e}")
        self.app.set_status("分析失败")

    def show_sentence(self, index: int) -> None:
        """在依存句法文字列表中定位到指定句子（点击输入区标记时调用）。"""
        if not self._dep_sentences or not (0 <= index < len(self._dep_sentences)):
            return
        target = f"【句子 S{index + 1}】"
        pos = self.dep_text.search(target, "1.0", "end")
        if pos:
            self.app.select_tab("syntax")
            try:
                self._sub_nb.set(self._SUB_TITLES["dep"])
            except Exception:
                pass
            self.dep_text.see(pos)
            self.dep_text.tag_add("highlight", f"{pos} linestart", f"{pos} lineend+1c")
            self.dep_text.tag_config("highlight",
                                     background=s.resolve(s.ACCENT_SOFT))
            self.after(1200, lambda: self.dep_text.tag_remove("highlight", "1.0", "end"))

    def run_api(self) -> None:
        text = self.app.get_text()
        if not text.strip():
            messagebox.showinfo("提示", "请先输入待分析文本。")
            return
        if not api_backend.is_configured():
            if messagebox.askyesno("API 未配置", "尚未配置 API，是否现在配置？"):
                self.app.open_api_settings()
            return
        if self._runner.is_running():
            return

        self.api_text.delete("1.0", "end")
        self.api_text.insert("end", "⏳ 正在调用 API，请稍候……\n")
        self.app.set_status("正在调用 AI API……")
        lang = self.app.get_lang()
        self._runner.run(
            api_backend.advanced_analysis,
            args=(text, self.api_task.get(), lang),
            on_success=self._on_api_result,
            on_error=self._on_error,
            title="AI 高级分析",
            message="正在调用在线 API，请稍候...",
        )

    def _on_api_result(self, result: str) -> None:
        self.api_text.delete("1.0", "end")
        self.api_text.insert("end", result)
        self.app.set_status("AI 分析完成")

    def export(self) -> None:
        if self._last is None:
            return
        from core.export import export_syntax_result
        export_syntax_result(self._last, self.winfo_toplevel())


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
        """检查输入并返回是否需要重新分析。"""
        text = self.app.get_text()
        if not text.strip():
            messagebox.showinfo("提示", "请先输入待分析文本。")
            return False
        lang = self.app.get_lang()
        cache_key = (text, lang)
        if (self._cache_key == cache_key
                and self._basic is not None
                and self._syntax is not None):
            return True
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

        self.file_btn = flat_btn(inner, text="📂 选择文件", command=self._load_file)
        self.file_btn.pack(side="left", padx=(0, 4))

        self.paste_btn = flat_btn(inner, text="📋 粘贴文本", command=self._paste_text)
        self.paste_btn.pack(side="left", padx=(0, 8))

        self.status_label = ctk.CTkLabel(
            inner, text="尚未加载文本",
            font=s.font("footnote"), text_color=s.MUTED,
        )
        self.status_label.pack(side="left")

        self.clear_btn = flat_btn(inner, text="✕ 清除", width=80,
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
        self.status_label.configure(text="尚未加载文本", text_color=s.MUTED)
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
        self.clear_btn.configure(text="✕ 移除", command=self._remove)

    def _remove(self) -> None:
        self.destroy()
        self.on_remove_cb(self)

    def redraw(self, new_index: int) -> None:
        self.index = new_index
        self.frame.set_title(f"🔍 对照作者 C{new_index}")


# ── FingerprintTab ──────────────────────────────────────────


class FingerprintTab(ctk.CTkScrollableFrame):
    """语言指纹分析标签页。

    布局：紧凑文件选择行 → 图表 → 详细报告。
    """

    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.control_rows: list[_ControlRow] = []

        # ── 运行控制 ──
        ctrl_card = Card(self, "▶ 运行控制")
        ctrl_card.pack(fill="x", padx=10, pady=(10, 4))
        ctrl = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        ctrl.pack(fill="x", padx=12, pady=(6, 10))
        self.run_btn = accent_btn(ctrl, text="▶ 运行语言指纹分析",
                                  command=self.run)
        self.run_btn.pack(side="left")
        self.export_btn = flat_btn(ctrl, text="📤 导出报告", command=self.export,
                                   state="disabled")
        self.export_btn.pack(side="left", padx=(8, 0))
        self._runner = TaskRunner(self)
        self._last: Optional[linguistic_fingerprint.FingerprintResult] = None
        ctk.CTkLabel(
            ctrl,
            text="  |  加载文件或粘贴文本，支持 txt / docx / pdf / html / rtf 等格式",
            font=s.font("footnote"), text_color=s.MUTED,
        ).pack(side="left", padx=8)

        # ── 输入设置：可疑文本 A ──
        self.row_a = _InputRow(
            self, "可疑文本 A（≥3000 字符）", "📝", min_chars=3000,
            on_change=self._update_status,
        )

        # ── 嫌疑作者 B ──
        self.row_b = _InputRow(
            self, "嫌疑作者 B 的已知作品", "👤", on_change=self._update_status,
        )

        # ── 对照作者容器 ──
        self.controls_container = ctk.CTkFrame(self, fg_color="transparent")
        self.controls_container.pack(fill="x", padx=0, pady=0)

        # 添加对照按钮
        add_frame = ctk.CTkFrame(self, fg_color="transparent")
        add_frame.pack(fill="x", padx=10, pady=(2, 4))
        self.add_btn = flat_btn(add_frame, text="+ 添加对照作者",
                                command=self._add_control)
        self.add_btn.pack(side="left")
        ctk.CTkLabel(
            add_frame,
            text="  添加同性别、同类型、同时期的其他作家作品作为对照",
            font=s.font("caption"), text_color=s.MUTED,
        ).pack(side="left", padx=6)

        # 默认添加一个对照
        self._add_control()

        # ── 结果展示：图表区域 ──
        self.chart_frame = Card(self, "📊 相似度对比图")
        self.chart_frame.pack(fill="x", padx=10, pady=(6, 2))
        self.chart_holder = ctk.CTkFrame(self.chart_frame, fg_color="transparent",
                                         height=260)
        self.chart_holder.pack(fill="x", padx=8, pady=8)
        self.chart_holder.pack_propagate(False)

        # ── 结果展示：详细报告 ──
        self.report_frame = Card(self, "📋 详细报告")
        self.report_frame.pack(fill="x", padx=10, pady=(4, 10))
        self.results_text = ctk.CTkTextbox(
            self.report_frame, wrap="word",
            font=s.font("footnote" if is_compact_mode() else "body"),
            height=220,
        )
        self.results_text.pack(fill="x", padx=12, pady=(4, 10))
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
        # 防重入：分析期间禁用按钮
        if self._runner.is_running():
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
        self.app.set_status("正在运行语言指纹分析……")
        self.results_text.delete("1.0", "end")
        self.results_text.insert("end", "⏳ 分析中，请稍候……\n")

        self._runner.run(
            linguistic_fingerprint.analyze_fingerprint,
            args=(suspect, author_b, controls, self.app.get_lang()),
            on_success=lambda res: self._on_result(res, a_len, author_b, controls),
            on_error=self._on_error,
            title="语言指纹分析",
            message="正在提取多维语言特征并执行统计检验...",
        )

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

    def export(self) -> None:
        if self._last is None:
            return
        from core.export import export_fingerprint_result
        export_fingerprint_result(self._last, self.winfo_toplevel())


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

        self._files: list[str] = []

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
        if self._runner.is_running():
            return

        self.export_btn.configure(state="disabled")
        self.app.set_status("正在批量分析文件……")
        self._runner.run(
            batch.analyze_files,
            args=(self._files, self.app.get_lang()),
            on_success=self._on_result,
            on_error=self._on_error,
            title="批量分析",
            message=f"正在分析 {len(self._files)} 个文件，请稍候...",
        )

    def _on_result(self, results: list) -> None:
        self._results = results
        clear_widget(self._list_body)
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

        ok_count = sum(1 for r in results if r.status == "ok")
        self.export_btn.configure(state="normal")
        self.app.set_status(f"批量分析完成 — {ok_count}/{len(results)} 成功")

    def _on_error(self, e: Exception) -> None:
        messagebox.showerror("错误", f"批量分析失败：{e}")
        self.app.set_status("批量分析失败")

    def export(self) -> None:
        if not self._results:
            return
        from core.export import export_batch_result
        export_batch_result(self._results, self.winfo_toplevel())


# --------------------------------------------------------------------------- #
# 批量实验（译者风格识别管线 GUI）
# --------------------------------------------------------------------------- #


class ExperimentTab(ctk.CTkScrollableFrame):
    """批量分组实验标签页：可选切片 + Burrows' Delta + 语言指纹统计检验。

    GUI 只负责收集参数、调用 experiments 包的核心函数并展示结果，
    不复制任何实验逻辑。
    """

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self._runner = TaskRunner(self)
        self._out_dir: Optional[str] = None

        # ══ 输入设置 ══
        input_card = Card(self, "📥 输入设置")
        input_card.pack(fill="x", padx=10, pady=(10, 4))

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
        opts.pack(fill="x", padx=12, pady=(2, 10))
        ctk.CTkLabel(opts, text="切片词数：", font=s.font("body")).pack(side="left")
        self.chunk_var = tk.StringVar(value="2000")
        ctk.CTkEntry(opts, textvariable=self.chunk_var, width=80,
                     font=s.font("body")).pack(side="left", padx=(4, 12))

        self.mode_var = tk.StringVar(value="slice")
        ctk.CTkRadioButton(
            opts, text="切片后实验（长文本）",
            variable=self.mode_var, value="slice",
            font=s.font("body"),
        ).pack(side="left", padx=(0, 8))
        ctk.CTkRadioButton(
            opts, text="直接实验（已切好/短文本）",
            variable=self.mode_var, value="direct",
            font=s.font("body"),
        ).pack(side="left")

        self.clean_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            opts, text="运行前清空输出目录",
            variable=self.clean_var,
            font=s.font("body"),
        ).pack(side="left", padx=(12, 0))

        # ══ 运行控制 ══
        ctrl_card = Card(self, "▶ 运行控制")
        ctrl_card.pack(fill="x", padx=10, pady=4)

        ctrl = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        ctrl.pack(fill="x", padx=12, pady=(6, 4))
        self.run_btn = accent_btn(ctrl, text="▶ 开始实验", command=self.run)
        self.run_btn.pack(side="left")
        self.open_btn = flat_btn(ctrl, text="📂 打开输出文件夹",
                                 command=self._open_output, state="disabled")
        self.open_btn.pack(side="left", padx=(8, 0))

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

        # ══ 结果展示：摘要网格 ══
        result_card = Card(self, "📋 实验结果摘要")
        result_card.pack(fill="x", padx=10, pady=(4, 10))

        self.metrics_grid = ctk.CTkFrame(result_card, fg_color="transparent")
        self.metrics_grid.pack(fill="x", padx=12, pady=(6, 4))
        self.metrics_grid.grid_columnconfigure(1, weight=1)
        self.metrics_grid.grid_columnconfigure(3, weight=1)

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
        self._placeholder_label.grid(row=0, column=0, columnspan=4,
                                     sticky="w", pady=4)

        self.conclusion_label = ctk.CTkLabel(
            result_card, text="",
            font=s.font("body", bold=True),
            anchor="w", justify="left", wraplength=820,
        )
        self.conclusion_label.pack(fill="x", padx=12, pady=(4, 2))

        self.out_dir_label = ctk.CTkLabel(
            result_card, text="",
            font=s.font("footnote"), text_color=s.MUTED,
            anchor="w", justify="left", wraplength=820,
        )
        self.out_dir_label.pack(fill="x", padx=12, pady=(0, 10))

    # ── 指标网格 ──
    def _metric(self, index: int, name: str, value: str,
                color=None) -> None:
        """在双栏网格中添加一行指标（显著=绿、不显著=灰）。"""
        row, lane = divmod(index, 2)
        c0 = lane * 2
        ctk.CTkLabel(
            self.metrics_grid, text=name,
            font=s.font("footnote"), text_color=s.MUTED,
            anchor="e", width=170,
        ).grid(row=row, column=c0, sticky="e", padx=(4, 6), pady=2)
        ctk.CTkLabel(
            self.metrics_grid, text=value,
            font=s.font("body", bold=True, mono=True),
            text_color=color if color is not None else s.TEXT,
            anchor="w",
        ).grid(row=row, column=c0 + 1, sticky="w", padx=(0, 24), pady=2)

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
        self.open_btn.configure(state="disabled")
        self.stage_var.set("准备中…")
        self.progress_bar.set(0)
        self.app.set_status("正在运行批量实验……")
        self._runner.run(
            self._do_experiment,
            args=(input_dir, out_dir, chunk_size, mode, clean),
            kwargs={"progress_callback": self._enqueue_progress},
            on_success=self._on_result,
            on_error=self._on_error,
            title="批量实验",
            message="正在执行切片与分组实验（Delta 聚类 + 指纹检验），请稍候...",
            show_dialog=False,
        )
        self._drain_progress()

    # ── 进度回调（后台线程）与主线程刷新 ──
    def _enqueue_progress(self, current: int, total: int, stage: str) -> None:
        """后台线程的进度回调：只入队，不碰 UI。"""
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

        self.conclusion_label.configure(text=f"【结论】{stats['conclusion']}")
        self.out_dir_label.configure(text=f"完整报告与图表见输出目录：{out_dir}")

        self.stage_var.set("完成")
        self.progress_bar.set(1)
        self.open_btn.configure(state="normal")
        self.run_btn.configure(state="normal")
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
        self.run_btn.configure(state="normal")
        self.app.set_status("批量实验失败")

    def _open_output(self) -> None:
        if not self._out_dir:
            return
        import subprocess
        import sys

        path = os.path.normpath(self._out_dir)
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开输出文件夹：{e}")
