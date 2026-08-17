"""各功能标签页。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from typing import Optional

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

import os

from core import analyzer, comparison, api_backend, history, linguistic_fingerprint, batch, file_io
from ui.async_runner import TaskRunner
from ui.style import (
    get_theme, register_theme_callback, is_compact_mode,
    get_screen_size, responsive_font_size,
    FONT, FONT_MONO, FONT_SCALE,
)
import ui.style as s


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #


def _help_text(msg: str) -> str:
    return msg


def clear_widget(w: tk.Widget) -> None:
    for child in w.winfo_children():
        child.destroy()


def embed_figure(parent: tk.Widget, fig: Figure) -> None:
    """将 matplotlib Figure 嵌入可滚动的容器中。"""
    # 关闭所有旧 Figure，防止内存泄漏
    plt.close("all")
    clear_widget(parent)
    t = get_theme()

    # 外层 Canvas + 滚动条（支持大图浏览）
    outer = tk.Canvas(parent, bg=t.BG, highlightthickness=0, bd=0)
    vsb = ttk.Scrollbar(parent, orient="vertical", command=outer.yview)
    hsb = ttk.Scrollbar(parent, orient="horizontal", command=outer.xview)
    outer.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    inner = ttk.Frame(outer)
    inner_id = outer.create_window((0, 0), window=inner, anchor="nw")

    mpl_canvas = FigureCanvasTkAgg(fig, master=inner)
    mpl_canvas.draw()
    mpl_canvas.get_tk_widget().pack(fill="both", expand=True)

    def _on_inner_conf(_event):
        outer.configure(scrollregion=outer.bbox("all"))

    def _on_outer_conf(event):
        # 让 inner frame 填充 Canvas 宽度
        outer.itemconfig(inner_id, width=event.width)

    inner.bind("<Configure>", _on_inner_conf)
    outer.bind("<Configure>", _on_outer_conf)

    # 按需显示滚动条
    def _check_scroll(_event=None):
        bbox = outer.bbox("all")
        if bbox:
            need_v = bbox[3] > outer.winfo_height() + 5
            need_h = bbox[2] > outer.winfo_width() + 5
            if need_v:
                vsb.pack(side="right", fill="y")
            else:
                vsb.pack_forget()
            if need_h:
                hsb.pack(side="bottom", fill="x")
            else:
                hsb.pack_forget()
        # 延迟再检查一次（matplotlib 渲染可能异步）
        outer.after(200, _check_scroll)

    inner.bind("<Configure>", lambda e: (_on_inner_conf(e), _check_scroll(e)), add=True)

    outer.pack(side="left", fill="both", expand=True)
    outer.after(300, _check_scroll)


def _apply_text_theme(st: scrolledtext.ScrolledText, t) -> None:
    """将主题颜色应用到一个 ScrolledText。"""
    try:
        st.configure(
            bg=t.INPUT_BG, fg=t.INPUT_FG,
            highlightbackground=t.BORDER,
            selectbackground=t.SELECT_BG,
        )
    except Exception:
        pass


def make_labeled_text(parent: tk.Widget, label: str) -> scrolledtext.ScrolledText:
    """创建一个带标题的 ScrolledText 面板，自动跟随主题。"""
    t = get_theme()
    lbl = ttk.Label(parent, text=label,
                    font=(FONT, responsive_font_size(FONT_SCALE["footnote"])),
                    foreground=t.MUTED)
    lbl.pack(anchor="w", pady=(6, 2))
    st = scrolledtext.ScrolledText(parent, wrap="word")
    st.pack(fill="both", expand=True, pady=(0, 4))

    # 注册主题更新回调
    def on_theme_change(theme):
        _apply_text_theme(st, theme)

    register_theme_callback(on_theme_change)
    return st


def _themed_text(parent: tk.Widget, **kwargs) -> tk.Text:
    """创建一个跟随主题的 tk.Text。"""
    t = get_theme()
    defaults = dict(
        font=(FONT, responsive_font_size(FONT_SCALE["body"])),
        bg=t.ROW_ALT, fg=t.TEXT,
        relief="flat", padx=10, pady=8, wrap="word",
    )
    defaults.update(kwargs)
    txt = tk.Text(parent, **defaults)

    def on_theme_change(theme):
        try:
            txt.configure(
                bg=theme.ROW_ALT if "bg" not in kwargs else kwargs.get("bg", theme.ROW_ALT),
                fg=theme.TEXT,
                highlightbackground=theme.BORDER,
                selectbackground=theme.SELECT_BG,
            )
        except Exception:
            pass

    register_theme_callback(on_theme_change)
    return txt


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
# --------------------------------------------------------------------------- #
# 依存句法树卡片（可折叠 + 可缩放）
# --------------------------------------------------------------------------- #


class _SentenceCard:
    """单句依存树的折叠卡片。

    折叠时只显示标题栏（句子编号 + 词数），展开后内嵌 matplotlib 树图
    并附带 NavigationToolbar2Tk 缩放工具栏。
    """

    def __init__(self, parent: tk.Widget, sent_index: int, sent_deps: list,
                 dark_mode: bool = False):
        self._sent_idx = sent_index
        self._deps = sent_deps
        self._dark = dark_mode
        self._expanded = False
        self._fig = None
        self._canvas = None

        n_words = len(sent_deps)
        self.frame = ttk.LabelFrame(
            parent,
            text=f"  S{sent_index + 1}  ·  {n_words} 词",
            style="Card.TLabelframe",
        )
        self.frame.pack(fill="x", padx=6, pady=3)

        # 标题栏（点击切换）
        hdr = ttk.Frame(self.frame)
        hdr.pack(fill="x", padx=6, pady=(4, 2))

        self._toggle_btn = ttk.Button(hdr, text="▶", width=3,
                                       command=self.toggle)
        self._toggle_btn.pack(side="left")

        root_word = _find_root_word(sent_deps)
        ttk.Label(hdr, text=f"ROOT: {root_word}",
                  font=(FONT, responsive_font_size(FONT_SCALE["footnote"]))).pack(
            side="left", padx=8)

        # 内容区（初始隐藏）
        self._content = ttk.Frame(self.frame)

    def toggle(self) -> None:
        if self._expanded:
            self._collapse()
        else:
            self._expand()

    def _expand(self) -> None:
        self._content.pack(fill="both", expand=True, padx=4, pady=(2, 6))
        self._toggle_btn.config(text="▼")
        self._expanded = True
        if self._fig is None:
            self.frame.after(50, self._draw_tree)

    def _collapse(self) -> None:
        self._content.pack_forget()
        self._toggle_btn.config(text="▶")
        self._expanded = False
        # 关闭 Figure 释放内存
        if self._fig is not None:
            try:
                plt.close(self._fig)
            except Exception:
                pass
            self._fig = None
            self._canvas = None

    def _draw_tree(self) -> None:
        from viz.plots import make_dependency_graph

        clear_widget(self._content)
        t = get_theme()
        dark = t.name == "dark"

        self._fig = make_dependency_graph(
            self._deps,
            title=f"S{self._sent_idx + 1}",
            dark_mode=dark,
            sentence_index=0,
        )
        self._canvas = FigureCanvasTkAgg(self._fig, master=self._content)
        self._canvas.draw()
        self._canvas.get_tk_widget().pack(fill="both", expand=True)

        # 缩放工具栏
        toolbar = NavigationToolbar2Tk(self._canvas, self._content)
        toolbar.update()
        toolbar.pack(fill="x")

    def update_theme(self, dark_mode: bool) -> None:
        """主题切换时重新绘制树图。"""
        # 先关闭旧 Figure，避免内存泄漏
        if self._fig is not None:
            try:
                plt.close(self._fig)
            except Exception:
                pass
        if self._expanded and self._fig is not None:
            from viz.plots import make_dependency_graph
            clear_widget(self._content)
            self._fig = make_dependency_graph(
                self._deps,
                title=f"S{self._sent_idx + 1}",
                dark_mode=dark_mode,
                sentence_index=0,
            )
            self._canvas = FigureCanvasTkAgg(self._fig, master=self._content)
            self._canvas.draw()
            self._canvas.get_tk_widget().pack(fill="both", expand=True)
            toolbar = NavigationToolbar2Tk(self._canvas, self._content)
            toolbar.update()
            toolbar.pack(fill="x")


def _find_root_word(sent_deps: list) -> str:
    for d in sent_deps:
        if d.get("dep") == "ROOT":
            return d.get("text", "?")
    return "?"


# --------------------------------------------------------------------------- #
# 基础分析
# --------------------------------------------------------------------------- #


class BasicTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self._runner = TaskRunner(self)

        ctrl = ttk.Frame(self)
        ctrl.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Button(ctrl, text="▶ 运行基础分析", style="Accent.TButton",
                   command=self.run).pack(side="left")
        self.export_btn = ttk.Button(ctrl, text="📤 导出结果", command=self.export,
                                      state="disabled")
        self.export_btn.pack(side="left", padx=(8, 0))

        # 摘要卡片（紧凑模式下减少高度）
        card = ttk.LabelFrame(self, text="📋 统计摘要", style="Card.TLabelframe")
        card.pack(fill="x", padx=10, pady=(2, 4))
        summary_h = 5 if is_compact_mode() else 7
        self.summary = _themed_text(card, height=summary_h)
        self.summary.pack(fill="x", padx=2, pady=2)

        # 分词 + 词频 双栏
        pane = ttk.PanedWindow(self, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=10, pady=4)

        left = ttk.Frame(pane)
        right = ttk.Frame(pane)
        pane.add(left)
        pane.add(right)

        self.tokens_text = make_labeled_text(
            left, "🔤 分词结果  —  词元 / 词性 / 词形还原"
        )
        self.freq_text = make_labeled_text(right, "📊 词频 Top 30")

        # ── 关键词上下文 KWIC ──
        kwic_frame = ttk.LabelFrame(self, text="🔍 关键词上下文 (KWIC)", style="Card.TLabelframe")
        kwic_frame.pack(fill="both", expand=False, padx=10, pady=(4, 8))

        kwic_ctrl = ttk.Frame(kwic_frame)        kwic_ctrl.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Label(kwic_ctrl, text="检索词：").pack(side="left")
        self.kwic_entry = ttk.Entry(kwic_ctrl, width=24)
        self.kwic_entry.pack(side="left", padx=(4, 8))
        ttk.Label(kwic_ctrl, text="窗口：").pack(side="left")
        self.kwic_window = tk.Spinbox(kwic_ctrl, from_=2, to=12, width=4)
        self.kwic_window.delete(0, "end")
        self.kwic_window.insert(0, "6")
        self.kwic_window.pack(side="left", padx=(4, 8))
        self.kwic_regex = tk.BooleanVar(value=False)
        ttk.Checkbutton(kwic_ctrl, text="正则", variable=self.kwic_regex).pack(side="left", padx=(0, 8))
        self.kwic_case = tk.BooleanVar(value=False)
        ttk.Checkbutton(kwic_ctrl, text="区分大小写", variable=self.kwic_case).pack(side="left", padx=(0, 8))
        ttk.Button(kwic_ctrl, text="🔍 搜索", command=self.run_kwic).pack(side="left")
        self.kwic_export_btn = ttk.Button(kwic_ctrl, text="📤 导出 KWIC", command=self.export_kwic,
                                           state="disabled")
        self.kwic_export_btn.pack(side="left", padx=(8, 0))

        self.kwic_text = make_labeled_text(kwic_frame, "")
        self.kwic_text.configure(height=8)
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


class SyntaxTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self._runner = TaskRunner(self)
        self._last: Optional[analyzer.SyntaxResult] = None

        ctrl = ttk.Frame(self)
        ctrl.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Button(ctrl, text="▶ 运行句法/语义分析", style="Accent.TButton",
                   command=self.run_local).pack(side="left")
        ttk.Button(ctrl, text="🤖 AI 高级分析", command=self.run_api).pack(side="left", padx=8)
        self.export_btn = ttk.Button(ctrl, text="📤 导出结果", command=self.export,
                                      state="disabled")
        self.export_btn.pack(side="left", padx=(8, 0))

        nb = ttk.Notebook(self, style="Sub.TNotebook")
        nb.pack(fill="both", expand=True, padx=10, pady=4)

        self.ner_tab = ttk.Frame(nb)
        self.kw_tab = ttk.Frame(nb)
        self.dep_tab = ttk.Frame(nb)
        self.sent_tab = ttk.Frame(nb)
        self.api_tab = ttk.Frame(nb)
        nb.add(self.ner_tab, text="  🏷 命名实体  ")
        nb.add(self.kw_tab, text="  🔑 关键词  ")
        nb.add(self.dep_tab, text="  🌳 依存句法  ")
        nb.add(self.sent_tab, text="  💬 情感分析  ")
        nb.add(self.api_tab, text="  🤖 AI 高级  ")

        self.ner_text = make_labeled_text(self.ner_tab, "命名实体  —  实体 / 类型")
        self.kw_text = make_labeled_text(self.kw_tab, "关键词  —  词语 / 权重")

        # ── 依存句法：文字列表（可视化请在「可视化」标签查看树图）──
        self.dep_text = make_labeled_text(            self.dep_tab,            "依存关系  —  词元(词性)  ──依存──▶  head(head词性)"
        )
        self._dep_sentences: list[list[dict]] = []

        self.sent_text = make_labeled_text(self.sent_tab, "情感得分  —  -1 负向  ~  1 正向")
        self.api_text = make_labeled_text(self.api_tab, "AI 返回结果")

        taskbar = ttk.Frame(self.api_tab)
        taskbar.pack(fill="x", pady=(4, 2))
        ttk.Label(taskbar, text="分析任务：").pack(side="left")
        self.api_task = tk.StringVar(value="综合语言学分析")
        ttk.Combobox(
            taskbar,
            textvariable=self.api_task,
            values=[
                "综合语言学分析",
                "句法结构分析",
                "文体风格分析",
                "翻译质量评估",
                "修辞手法分析",
            ],
            width=24,
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
        t = get_theme()

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
                        self.dep_text.insert(                            "end",
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
            try:
                self.master.select(self)
            except Exception:
                pass
            self.dep_text.see(pos)
            self.dep_text.tag_add("highlight", f"{pos} linestart", f"{pos} lineend+1c")
            self.dep_text.tag_configure("highlight", background=get_theme().ACCENT_SOFT)
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


class CompareTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self._runner = TaskRunner(self)
        self._last_readability = None
        self._last_alignment = None

        ctrl = ttk.Frame(self)
        ctrl.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Button(ctrl, text="▶ 分析可读性", style="Accent.TButton",
                   command=self.run_readability).pack(side="left")
        self.export_read_btn = ttk.Button(ctrl, text="📤 导出可读性", command=self.export_readability,
                                           state="disabled")
        self.export_read_btn.pack(side="left", padx=(8, 0))

        # 双输入框
        pane = ttk.PanedWindow(self, orient="horizontal")
        pane.pack(fill="both", expand=True, padx=10, pady=4)
        left = ttk.Frame(pane)
        right = ttk.Frame(pane)
        pane.add(left)
        pane.add(right)

        ttk.Label(left, text="中文原文",
                  font=(FONT, responsive_font_size(FONT_SCALE["footnote"])),
                  foreground=s.MUTED).pack(anchor="w")
        self.zh_box = scrolledtext.ScrolledText(left, wrap="word")
        self.zh_box.pack(fill="both", expand=True)

        ttk.Label(right, text="英文原文",
                  font=(FONT, responsive_font_size(FONT_SCALE["footnote"])),
                  foreground=s.MUTED).pack(anchor="w")
        self.en_box = scrolledtext.ScrolledText(right, wrap="word")
        self.en_box.pack(fill="both", expand=True)

        ctrl2 = ttk.Frame(self)
        ctrl2.pack(fill="x", padx=10, pady=2)
        ttk.Button(ctrl2, text="🔗 对齐中英句子", command=self.run_align).pack(side="left")
        self.export_align_btn = ttk.Button(ctrl2, text="📤 导出对齐", command=self.export_alignment,
                                            state="disabled")
        self.export_align_btn.pack(side="left", padx=(8, 0))
        ttk.Button(ctrl2, text="📥 从主输入框填入", command=self.fill_from_main).pack(side="left", padx=(8, 0))

        self.out = make_labeled_text(self, "📋 结果输出")

        # 注册对比输入框的主题回调
        def on_theme_change(theme):
            for box in (self.zh_box, self.en_box):
                _apply_text_theme(box, theme)

        register_theme_callback(on_theme_change)

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


class HistoryTab(ttk.Frame):
    """展示过往分析记录，点击可回溯输入文本。"""

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        ctrl = ttk.Frame(self)
        ctrl.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Button(ctrl, text="🔄 刷新列表", command=self.refresh).pack(side="left")
        ttk.Button(ctrl, text="🗑 清空历史", command=self.clear).pack(side="left", padx=8)
        ttk.Label(
            ctrl,
            text="双击某条记录可将其文本载入主输入框",
            font=(FONT, responsive_font_size(FONT_SCALE["footnote"])),
            foreground=s.MUTED,
        ).pack(side="left", padx=12)

        # 列表
        cols = ("#1", "时间", "语言", "关键词 / 实体", "情感")
        self.tree = ttk.Treeview(
            self, columns=cols, show="headings",
            selectmode="browse", height=12,
        )
        self.tree.heading("#1", text="时间")
        self.tree.heading("时间", text="语言")
        self.tree.heading("语言", text="输入摘要")
        self.tree.heading("关键词 / 实体", text="关键词 / 实体")
        self.tree.heading("情感", text="情感")

        self.tree.column("#1", width=130, anchor="w")
        self.tree.column("时间", width=60, anchor="center")
        self.tree.column("语言", width=220, anchor="w")
        self.tree.column("关键词 / 实体", width=280, anchor="w")
        self.tree.column("情感", width=72, anchor="center")

        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=4)
        vsb.pack(side="right", fill="y", pady=4, padx=(0, 10))

        self.tree.bind("<Double-1>", self._on_double_click)

        # 详情面板（紧凑模式下减少高度）
        detail_h = 5 if is_compact_mode() else 8
        self.detail = _themed_text(self, height=detail_h)
        self.detail.pack(fill="x", padx=10, pady=(4, 10))

        self._entries: list[history.HistoryEntry] = []
        self.refresh()

    def refresh(self) -> None:
        self._entries = history.load_all()
        self._entries.reverse()
        self.tree.delete(*self.tree.get_children())
        for e in self._entries:
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
            self.tree.insert(
                "", "end",
                iid=e.id,
                values=(e.timestamp[:19], lang, inp, kw_or_ner, sent),
            )

    def clear(self) -> None:
        if messagebox.askyesno("确认", "确定清空全部历史记录？此操作不可撤销。"):
            history.clear_all()
            self.refresh()
            self.detail.delete("1.0", "end")

    def _on_double_click(self, event) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        eid = sel[0]
        entry = next((e for e in self._entries if e.id == eid), None)
        if entry is None:
            return
        # 载入输入文本
        self.app.text.delete("1.0", "end")
        self.app.text.insert("end", entry.input_text)
        t = get_theme()
        self.app.text.config(fg=t.TEXT)
        self.app._placeholder_shown = False
        # 根据语言设置下拉
        lang_map = {"中文": "中文", "英文": "英文", "中英混合": "中英混合"}
        self.app.lang_var.set(lang_map.get(entry.lang, "自动"))
        # 显示详情
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
        self.app.set_status(f"已载入历史记录 — {entry.timestamp[:19]}")


# --------------------------------------------------------------------------- #
# 可视化
# --------------------------------------------------------------------------- #


class VizTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self._runner = TaskRunner(self)
        from viz import plots
        self.plots = plots

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=10, pady=(10, 4))
        buttons = [
            ("☁ 词云", "wordcloud"),
            ("📊 词频柱状图", "freq"),
            ("🥧 词性饼图", "pos"),
            ("🌳 依存句法图", "dep"),
            ("📈 情感趋势图", "sent"),
        ]
        for label, kind in buttons:
            ttk.Button(bar, text=label, command=lambda k=kind: self.draw(k)).pack(
                side="left", padx=(0, 6)
            )

        self.canvas_holder = ttk.Frame(self)
        self.canvas_holder.pack(fill="both", expand=True, padx=10, pady=4)
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
            self._draw(kind)
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
        self._draw(kind)

    def _draw(self, kind: str) -> None:
        self.app.set_status(f"正在生成图表: {kind}……")
        t = get_theme()
        dark = t.name == "dark"
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
    """一个紧凑的文本输入行：文件选择按钮 + 粘贴按钮 + 状态标签。

    替换旧版的大块 ScrolledText，适合 3000+ 字符的长文本输入场景。
    """

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

        self.frame = ttk.LabelFrame(parent, text=f"{icon} {label}",
                                    style="Card.TLabelframe")
        self.frame.pack(fill="x", padx=10, pady=(3, 2))

        inner = ttk.Frame(self.frame)
        inner.pack(fill="x", padx=6, pady=(4, 4))

        self.file_btn = ttk.Button(inner, text="📂 选择文件", command=self._load_file)
        self.file_btn.pack(side="left", padx=(0, 4))

        self.paste_btn = ttk.Button(inner, text="📋 粘贴文本", command=self._paste_text)
        self.paste_btn.pack(side="left", padx=(0, 8))

        self.status_label = ttk.Label(
            inner, text="尚未加载文本",
            font=(FONT, responsive_font_size(FONT_SCALE["footnote"])),
            foreground=s.MUTED,
        )
        self.status_label.pack(side="left")

        self.clear_btn = ttk.Button(inner, text="✕ 清除", command=self._clear)
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
                self.status_label.config(text="⚠ 文件为空", foreground=s.DANGER)
                return
            self._text = text
            self.status_label.config(text=label_text, foreground=s.SUCCESS)
            if self.on_change:
                self.on_change()
        except Exception as e:
            messagebox.showerror("读取失败", str(e))

    # ── 粘贴文本 ──
    def _paste_text(self) -> None:
        """弹出粘贴窗口。按 Enter 确认，Shift+Enter 换行。"""
        popup = tk.Toplevel(self.frame)
        popup.title(f"粘贴文本 — {self.label}")
        # 响应式尺寸
        _, sh = get_screen_size()
        pw, ph = (580, 340) if sh <= 768 else (720, 420)
        popup.geometry(f"{pw}x{ph}")
        popup.minsize(480, 280)
        popup.transient(self.frame)
        popup.grab_set()

        box = scrolledtext.ScrolledText(popup, wrap="word",
             font=(FONT, responsive_font_size(FONT_SCALE["headline"])))
        box.pack(fill="both", expand=True, padx=8, pady=8)
        # 预填已有文本
        if self._text:
            box.insert("1.0", self._text)

        btn_frame = ttk.Frame(popup)
        btn_frame.pack(fill="x", padx=8, pady=(0, 8))

        # 提示文字
        ttk.Label(
            btn_frame, text="按 Enter 确认  ·  Shift+Enter 换行",
            font=(FONT, responsive_font_size(FONT_SCALE["caption"])),
            foreground=s.MUTED,
        ).pack(side="left", padx=(0, 8))

        def _confirm(event=None):
            text = box.get("1.0", "end-1c").strip()
            self._text = text
            count = len(re.sub(r"\s", "", text))
            warn = ""
            if self.min_chars > 0 and 0 < count < self.min_chars:
                warn = f"  ⚠ 不足 {self.min_chars} 字符"
            self.status_label.config(
                text=f"📋 手动粘贴  —  {count:,} 字符{warn}",
                foreground=s.DANGER if warn else s.SUCCESS,
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

        ttk.Button(btn_frame, text="✅ 确认", command=_confirm).pack(side="right", padx=4)
        ttk.Button(btn_frame, text="取消", command=popup.destroy).pack(side="right")

    # ── 清除 ──
    def _clear(self) -> None:
        self._text = ""
        self.status_label.config(text="尚未加载文本", foreground=s.MUTED)
        if self.on_change:
            self.on_change()

    # ── 公共 API ──
    def get_text(self) -> str:
        return self._text

    def set_text(self, text: str, label: str = "") -> None:
        """直接设置文本（供程序调用）。"""
        self._text = text
        count = len(re.sub(r"\s", "", text))
        self.status_label.config(
            text=label if label else f"已设置  —  {count:,} 字符",
            foreground=s.SUCCESS,
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
        self.frame.configure(text=f"🔍 对照作者 C{new_index}")


# ── 粘贴文本弹窗 ──────────────────────────────────────────


def _open_paste_popup(parent: tk.Widget, title: str, initial_text: str,
                      callback: "callable") -> None:
    """打开粘贴文本的模态弹窗。按 Enter 确认，Shift+Enter 换行。"""
    popup = tk.Toplevel(parent)
    popup.title(title)
    _, sh = get_screen_size()
    pw, ph = (560, 320) if sh <= 768 else (700, 400)
    popup.geometry(f"{pw}x{ph}")
    popup.minsize(460, 260)
    popup.transient(parent)
    popup.grab_set()

    box = scrolledtext.ScrolledText(popup, wrap="word",
         font=(FONT, responsive_font_size(FONT_SCALE["headline"])))
    box.pack(fill="both", expand=True, padx=8, pady=8)
    if initial_text:
        box.insert("1.0", initial_text)

    btn_frame = ttk.Frame(popup)
    btn_frame.pack(fill="x", padx=8, pady=(0, 8))

    ttk.Label(
        btn_frame, text="按 Enter 确认  ·  Shift+Enter 换行",
        font=(FONT, responsive_font_size(FONT_SCALE["caption"])),
        foreground=s.MUTED,
    ).pack(side="left", padx=(0, 8))

    def _done(event=None):
        callback(box.get("1.0", "end-1c").strip())
        popup.destroy()

    def _shift_return(event):
        box.insert("insert", "\n")
        return "break"

    box.bind("<Return>", _done)
    box.bind("<Shift-Return>", _shift_return)

    ttk.Button(btn_frame, text="✅ 确认", command=_done).pack(side="right", padx=4)
    ttk.Button(btn_frame, text="取消", command=popup.destroy).pack(side="right")


# ── FingerprintTab（重构版）────────────────────────────────


class FingerprintTab(ttk.Frame):
    """语言指纹分析标签页（重构版）。

    布局改为：紧凑文件选择行 → 图表 → 详细报告。
    旧版的大文本输入框全部替换为「📂 选择文件 + 📋 粘贴文本」行。
    """

    def __init__(self, master, app) -> None:
        super().__init__(master)
        self.app = app
        self.control_rows: list[_ControlRow] = []

        # ── 控制栏 ──
        ctrl = ttk.Frame(self)
        ctrl.pack(fill="x", padx=10, pady=(10, 4))
        self.run_btn = ttk.Button(
            ctrl, text="▶ 运行语言指纹分析", style="Accent.TButton",
            command=self.run,
        )
        self.run_btn.pack(side="left")
        self.export_btn = ttk.Button(ctrl, text="📤 导出报告", command=self.export,
                                      state="disabled")
        self.export_btn.pack(side="left", padx=(8, 0))
        self._runner = TaskRunner(self)
        self._last: Optional[linguistic_fingerprint.FingerprintResult] = None
        ttk.Label(
            ctrl,
            text="  |  加载文件或粘贴文本，支持 txt / docx / pdf / html / rtf 等格式",
            font=(FONT, responsive_font_size(FONT_SCALE["footnote"])),
            foreground=s.MUTED,
        ).pack(side="left", padx=8)

        # ── 可疑文本 A ──
        self.row_a = _InputRow(
            self, "可疑文本 A（≥3000 字符）", "📝", min_chars=3000,
            on_change=self._update_status,
        )

        # ── 嫌疑作者 B ──
        self.row_b = _InputRow(
            self, "嫌疑作者 B 的已知作品", "👤", on_change=self._update_status,
        )

        # ── 对照作者容器 ──
        self.controls_container = ttk.Frame(self)
        self.controls_container.pack(fill="x", padx=0, pady=0)

        # 添加对照按钮
        add_frame = ttk.Frame(self)
        add_frame.pack(fill="x", padx=10, pady=(2, 4))
        self.add_btn = ttk.Button(
            add_frame, text="+ 添加对照作者", command=self._add_control,
        )
        self.add_btn.pack(side="left")
        ttk.Label(
            add_frame,
            text="  添加同性别、同类型、同时期的其他作家作品作为对照",
            font=(FONT, responsive_font_size(FONT_SCALE["caption"])),
            foreground=s.MUTED,
        ).pack(side="left", padx=6)

        # 默认添加一个对照
        self._add_control()

        # ── 图表区域 ──
        self.chart_frame = ttk.LabelFrame(self, text="📊 相似度对比图",
                                          style="Card.TLabelframe")
        self.chart_frame.pack(fill="both", expand=True, padx=10, pady=(6, 2))
        self.chart_holder = ttk.Frame(self.chart_frame)
        self.chart_holder.pack(fill="both", expand=True, padx=4, pady=4)

        # ── 详细报告（主区域，expand）──
        self.report_frame = ttk.LabelFrame(self, text="📋 详细报告",
                                           style="Card.TLabelframe")
        self.report_frame.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.results_text = scrolledtext.ScrolledText(
            self.report_frame, wrap="word",
            font=(FONT, responsive_font_size(FONT_SCALE["footnote"])
                  if is_compact_mode() else responsive_font_size(FONT_SCALE["body"])),
        )
        self.results_text.pack(fill="both", expand=True, padx=4, pady=4)
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

        # 注册主题
        _apply_text_theme(self.results_text, get_theme())

        def on_theme_change(theme):
            _apply_text_theme(self.results_text, theme)

        register_theme_callback(on_theme_change)

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
        from ui.style import get_theme as _gt

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
        from ui.style import get_theme as _gt
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
        dark = _gt().name == "dark"
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


class BatchTab(ttk.Frame):
    """批量分析多个文件，输出聚合统计表格。"""

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self._runner = TaskRunner(self)
        self._results: list = []

        ctrl = ttk.Frame(self)
        ctrl.pack(fill="x", padx=10, pady=(10, 4))
        ttk.Button(ctrl, text="📂 选择文件", command=self.select_files).pack(side="left")
        ttk.Button(ctrl, text="▶ 开始批量分析", style="Accent.TButton",
                   command=self.run).pack(side="left", padx=(8, 0))
        self.export_btn = ttk.Button(ctrl, text="📤 导出结果", command=self.export,
                                      state="disabled")
        self.export_btn.pack(side="left", padx=(8, 0))

        # 文件列表 + 结果表格
        cols = ("文件名", "状态", "语言", "字符数", "词元数", "句子数", "不重复词", "Top 词")
        self.tree = ttk.Treeview(
            self, columns=cols, show="headings",
            selectmode="browse", height=14,
        )
        for c in cols:
            self.tree.heading(c, text=c)
        self.tree.column("文件名", width=180, anchor="w")
        self.tree.column("状态", width=60, anchor="center")
        self.tree.column("语言", width=70, anchor="center")
        self.tree.column("字符数", width=70, anchor="e")
        self.tree.column("词元数", width=70, anchor="e")
        self.tree.column("句子数", width=70, anchor="e")
        self.tree.column("不重复词", width=70, anchor="e")
        self.tree.column("Top 词", width=240, anchor="w")

        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=4)
        vsb.pack(side="right", fill="y", pady=4, padx=(0, 10))

        self._files: list[str] = []

    def select_files(self) -> None:
        paths = filedialog.askopenfilenames(filetypes=file_io.FILETYPES)
        if not paths:
            return
        self._files = list(paths)
        self._refresh_list()
        self.app.set_status(f"已选择 {len(self._files)} 个文件")

    def _refresh_list(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for p in self._files:
            self.tree.insert("", "end", values=(os.path.basename(p), "待分析", "", "", "", "", "", ""))

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
        self.tree.delete(*self.tree.get_children())
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
            self.tree.insert("", "end", values=values)

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


class ExperimentTab(ttk.Frame):
    """批量分组实验标签页：可选切片 + Burrows' Delta + 语言指纹统计检验。

    GUI 只负责收集参数、调用 experiments 包的核心函数并展示结果，
    不复制任何实验逻辑。
    """

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self._runner = TaskRunner(self)
        self._out_dir: Optional[str] = None

        # ── 语料目录 ──
        row1 = ttk.Frame(self)
        row1.pack(fill="x", padx=10, pady=(10, 2))
        ttk.Label(row1, text="语料目录：").pack(side="left")
        self.input_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self.input_var).pack(
            side="left", fill="x", expand=True, padx=(4, 4))
        ttk.Button(row1, text="📂 浏览…", command=self._pick_input).pack(side="left")

        ttk.Label(
            self,
            text="目录需按 一级子文件夹=组别（译者） 组织，每个组文件夹内放该组的 .txt 样本",
            font=(FONT, responsive_font_size(FONT_SCALE["caption"])),
            foreground=s.MUTED,
        ).pack(anchor="w", padx=10, pady=(0, 4))

        # ── 输出目录 ──
        row2 = ttk.Frame(self)
        row2.pack(fill="x", padx=10, pady=2)
        ttk.Label(row2, text="输出目录：").pack(side="left")
        self.output_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.output_var).pack(
            side="left", fill="x", expand=True, padx=(4, 4))
        ttk.Button(row2, text="📂 浏览…", command=self._pick_output).pack(side="left")

        ttk.Label(
            self,
            text="留空则默认为 语料目录/experiment_output",
            font=(FONT, responsive_font_size(FONT_SCALE["caption"])),
            foreground=s.MUTED,
        ).pack(anchor="w", padx=10, pady=(0, 4))

        # ── 选项行：切片词数 + 运行模式 ──
        opts = ttk.Frame(self)
        opts.pack(fill="x", padx=10, pady=2)
        ttk.Label(opts, text="切片词数：").pack(side="left")
        self.chunk_var = tk.StringVar(value="2000")
        ttk.Entry(opts, textvariable=self.chunk_var, width=8).pack(
            side="left", padx=(4, 12))

        self.mode_var = tk.StringVar(value="slice")
        ttk.Radiobutton(
            opts, text="切片后实验（长文本）",
            variable=self.mode_var, value="slice",
        ).pack(side="left", padx=(0, 8))
        ttk.Radiobutton(
            opts, text="直接实验（已切好/短文本）",
            variable=self.mode_var, value="direct",
        ).pack(side="left")

        # ── 开始按钮 ──
        ctrl = ttk.Frame(self)
        ctrl.pack(fill="x", padx=10, pady=(6, 2))
        self.run_btn = ttk.Button(
            ctrl, text="▶ 开始实验", style="Accent.TButton", command=self.run)
        self.run_btn.pack(side="left")
        self.open_btn = ttk.Button(
            ctrl, text="📂 打开输出文件夹", command=self._open_output,
            state="disabled")
        self.open_btn.pack(side="left", padx=(8, 0))

        # ── 结果摘要 ──
        card = ttk.LabelFrame(self, text="📋 实验结果摘要", style="Card.TLabelframe")
        card.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        self.result_text = scrolledtext.ScrolledText(
            card, wrap="word",
            font=(FONT_MONO, responsive_font_size(FONT_SCALE["body"])),
        )
        self.result_text.pack(fill="both", expand=True, padx=4, pady=4)
        self.result_text.insert(
            "end",
            "请选择语料目录后点击「▶ 开始实验」。\n\n"
            "流程：\n"
            "  1. （可选）按切片词数把长文本切成定长切片\n"
            "  2. 对全部样本计算 Burrows' Delta 距离矩阵并聚类\n"
            "  3. 计算语言指纹两两相似度，做 Wilcoxon / 置换检验 / Cohen's d\n"
            "  4. 输出 delta_matrix.csv、dendrogram.png、fingerprint_pairs.csv、report.md\n",
        )

        def on_theme_change(theme):
            _apply_text_theme(self.result_text, theme)

        register_theme_callback(on_theme_change)
        _apply_text_theme(self.result_text, get_theme())

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
        self.run_btn.configure(state="disabled")
        self.open_btn.configure(state="disabled")
        self.app.set_status("正在运行批量实验……")
        self._runner.run(
            self._do_experiment,
            args=(input_dir, out_dir, chunk_size, mode),
            on_success=self._on_result,
            on_error=self._on_error,
            title="批量实验",
            message="正在执行切片与分组实验（Delta 聚类 + 指纹检验），请稍候...",
        )

    @staticmethod
    def _do_experiment(input_dir: str, out_dir: str, chunk_size: int,
                       mode: str) -> tuple:
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
                written = slice_corpus(Path(input_dir), sliced_dir, chunk_size)
                if not written:
                    raise ValueError(
                        "切片结果为空：所有文本都短于 0.5 × 切片词数，"
                        "请减小切片词数，或改用「直接实验」。"
                    )
                exp_input = sliced_dir

            stats = run_experiment(exp_input, Path(out_dir))
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

        lines = [
            f"样本：{stats['n_samples']} 个，分 {len(stats['groups'])} 组（{groups_str}）",
            "",
            "【Burrows' Delta】",
            f"  组内平均 Delta：{stats['within_delta_mean']:.4f}",
            f"  组间平均 Delta：{stats['cross_delta_mean']:.4f}",
            f"  差值（组间 − 组内）：{stats['delta_diff']:.4f}",
            f"  比值（组间 / 组内）：{ratio_str}",
            "",
            "【语言指纹相似度】",
            f"  同译者对平均：{stats['same_sim_mean']:.4f}",
            f"  跨译者对平均：{stats['cross_sim_mean']:.4f}",
            f"  Wilcoxon 符号秩检验：p = {stats['p_wilcoxon']:.4f}",
            f"  置换检验：p = {stats['p_permutation']:.4f}",
            f"  Cohen's d = {stats['cohens_d']:.3f}",
            "",
            "【结论】",
            stats["conclusion"],
            "",
            f"完整报告与图表见输出目录：{out_dir}",
        ]
        self.result_text.delete("1.0", "end")
        self.result_text.insert("end", "\n".join(lines))

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
