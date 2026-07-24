"""Tkinter 主窗口：输入区、语言选择、标签页、菜单、API 设置与主题切换。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog

from core import analyzer, api_backend, file_io
from ui.style import (
    apply_style,
    get_theme,
    toggle_theme,
    register_theme_callback,
    enable_dpi_awareness,
    FONT,
    FONT_MONO,
)
from ui.tabs import BasicTab, SyntaxTab, CompareTab, VizTab, HistoryTab, FingerprintTab

import ui.style as s


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("汉英 NLP 分析工具")
        root.geometry("1280x820")
        root.minsize(1024, 680)
        root.configure(bg=s.BG)

        apply_style(root)
        self._theme_widgets: list[tk.Widget] = []
        self._build_header()
        self._build_menu()
        self._build_body()
        self._build_statusbar()
        self._show_status_hint()

    # ----------------------------------------------------------------- #
    # 头部
    # ----------------------------------------------------------------- #

    def _build_header(self) -> None:
        t = get_theme()
        bar = tk.Frame(
            self.root, bg=t.CARD,
            highlightthickness=0,
        )
        bar.pack(fill="x")

        # 底部阴影线
        shadow = tk.Frame(self.root, bg=t.BORDER, height=1)
        shadow.pack(fill="x")
        self._shadow = shadow  # 跟踪用于主题切换

        inner = tk.Frame(bar, bg=t.CARD)
        inner.pack(fill="x", padx=20, pady=(14, 6))

        # 左侧：标题与副标题
        left = tk.Frame(inner, bg=t.CARD)
        left.pack(side="left")

        tk.Label(
            left, text="📝 汉英 NLP 分析工具",
            font=(FONT, 15, "bold"),
            bg=t.CARD, fg=t.TEXT,
        ).pack(side="left")

        tk.Label(
            left, text="  汉语 · 英语 · 本地优先 · 可选 AI",
            font=(FONT, 9), bg=t.CARD, fg=t.MUTED,
        ).pack(side="left", padx=(6, 0))

        # 右侧：后端状态 + 主题切换
        right = tk.Frame(inner, bg=t.CARD)
        right.pack(side="right")

        self.backend_indicator = tk.Label(
            right, text="", font=(FONT, 9), bg=t.CARD, fg=t.SUCCESS,
        )
        self.backend_indicator.pack(side="left", padx=(0, 10))
        self._update_backend_indicator()

        # tk.Button 确保文字在所有系统上可见
        self.theme_btn = tk.Button(
            right,
            text="☾ 深色模式",
            font=(FONT, 9),
            bg=t.ACCENT_SOFT, fg=t.ACCENT,
            relief="flat", padx=12, pady=4,
            activebackground=t.ACCENT, activeforeground="#ffffff",
            borderwidth=0, cursor="hand2",
            command=self._toggle_theme,
        )
        self.theme_btn.pack(side="left")

        # 注册头部组件以支持主题更新
        for w in (bar, inner, left, right, self.backend_indicator):
            self._theme_widgets.append(w)

    def _toggle_theme(self) -> None:
        new_name = toggle_theme(self.root)
        t = get_theme()
        if new_name == "dark":
            self.theme_btn.config(text="☀ 浅色模式", bg=t.ACCENT_SOFT, fg=t.ACCENT,
                                  activebackground=t.ACCENT, activeforeground="#ffffff")
        else:
            self.theme_btn.config(text="☾ 深色模式", bg=t.ACCENT_SOFT, fg=t.ACCENT,
                                  activebackground=t.ACCENT, activeforeground="#ffffff")
        self._apply_theme_to_tk_widgets()

    def _apply_theme_to_tk_widgets(self) -> None:
        """手动更新所有已记录的 tk 组件颜色（ttk 组件已由 apply_style 处理）。"""
        t = get_theme()
        for w in self._theme_widgets:
            try:
                if isinstance(w, tk.Frame) or isinstance(w, tk.Toplevel):
                    w.configure(bg=t.CARD if hasattr(w, '_is_card') else t.BG)
                elif isinstance(w, tk.Label):
                    w.configure(bg=t.CARD if w.master and getattr(w.master, '_is_card', False) else t.BG)
                elif isinstance(w, tk.Text):
                    w.configure(bg=t.INPUT_BG, fg=t.INPUT_FG,
                                highlightbackground=t.BORDER,
                                selectbackground=t.SELECT_BG)
            except Exception:
                pass
        # 更新阴影线
        if hasattr(self, '_shadow'):
            self._shadow.configure(bg=t.BORDER)
        # 更新菜单
        self._rebuild_menu_colors()
        # 更新状态栏
        if hasattr(self, '_status'):
            self._status.configure(bg=t.ROW_ALT, fg=t.MUTED)

    def _update_backend_indicator(self) -> None:
        st = analyzer.selfcheck()
        ok_count = sum(1 for v in st.values() if v)
        total = len(st)
        t = get_theme()
        self.backend_indicator.config(
            text=f"后端: {ok_count}/{total} 就绪" if ok_count < total else "✓ 全部后端就绪",
            fg=t.SUCCESS if ok_count == total else t.MUTED,
        )

    # ----------------------------------------------------------------- #
    # 菜单
    # ----------------------------------------------------------------- #

    def _build_menu(self) -> None:
        self._rebuild_menu_colors()

    def _rebuild_menu_colors(self) -> None:
        t = get_theme()
        menubar = tk.Menu(self.root, bg=t.CARD, fg=t.TEXT,
                          activebackground=t.ACCENT_SOFT, activeforeground=t.TEXT,
                          borderwidth=0, font=(FONT, 10))

        mfile = tk.Menu(menubar, tearoff=0, bg=t.CARD, fg=t.TEXT,
                        activebackground=t.ACCENT_SOFT, activeforeground=t.TEXT,
                        font=(FONT, 10))
        mfile.add_command(label="📂 打开文件…", command=self.open_file, accelerator="Ctrl+O")
        mfile.add_command(label="💾 保存结果…", command=self.save_file, accelerator="Ctrl+S")
        mfile.add_separator()
        mfile.add_command(label="退出", command=self.root.quit)
        menubar.add_cascade(label="文件", menu=mfile)

        mset = tk.Menu(menubar, tearoff=0, bg=t.CARD, fg=t.TEXT,
                       activebackground=t.ACCENT_SOFT, activeforeground=t.TEXT,
                       font=(FONT, 10))
        mset.add_command(label="🔌 API 配置…", command=self.open_api_settings)
        mset.add_command(label="📋 检查后端状态", command=self.show_backend_status)
        mset.add_separator()
        theme_label = "☀️ 切换到浅色模式" if t.name == "dark" else "🌙 切换到深色模式"
        mset.add_command(label=theme_label, command=self._toggle_theme)
        menubar.add_cascade(label="设置", menu=mset)

        mhelp = tk.Menu(menubar, tearoff=0, bg=t.CARD, fg=t.TEXT,
                        activebackground=t.ACCENT_SOFT, activeforeground=t.TEXT,
                        font=(FONT, 10))
        mhelp.add_command(label="关于", command=self.about)
        menubar.add_cascade(label="帮助", menu=mhelp)

        self.root.config(menu=menubar)
        self.root.bind("<Control-o>", lambda e: self.open_file())
        self.root.bind("<Control-s>", lambda e: self.save_file())

    # ----------------------------------------------------------------- #
    # 主体
    # ----------------------------------------------------------------- #

    def _build_body(self) -> None:
        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True, padx=12, pady=(8, 4))

        # 左面板：输入
        left = ttk.LabelFrame(body, text="📥 输入文本", style="Card.TLabelframe")
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))

        ctrl = ttk.Frame(left)
        ctrl.pack(fill="x", padx=10, pady=(10, 2))
        ttk.Label(ctrl, text="检测语言：").pack(side="left")
        self.lang_var = tk.StringVar(value="自动")
        ttk.Combobox(
            ctrl,
            textvariable=self.lang_var,
            values=["自动", "中文", "英文", "中英混合"],
            width=10,
            state="readonly",
        ).pack(side="left", padx=(4, 12))
        ttk.Button(ctrl, text="📋 加载示例", command=self.load_sample).pack(side="right", padx=(4, 0))
        ttk.Button(ctrl, text="🗑 清空", command=self.clear_text).pack(side="right")

        t = get_theme()
        self.text = scrolledtext.ScrolledText(
            left, wrap="word", font=(FONT_MONO, 11),
            bg=t.INPUT_BG, fg=t.TEXT,
            highlightthickness=1, highlightbackground=t.BORDER,
            highlightcolor=t.ACCENT,
            selectbackground=t.SELECT_BG, selectforeground=t.TEXT,
            insertbackground=t.TEXT,
        )
        self.text.pack(fill="both", expand=True, padx=10, pady=(4, 10))

        # 注册主题回调
        def _on_text_theme_change(th):
            self.text.config(
                bg=th.INPUT_BG,
                highlightbackground=th.BORDER,
                highlightcolor=th.ACCENT,
                selectbackground=th.SELECT_BG, selectforeground=th.TEXT,
                insertbackground=th.TEXT,
            )
            if self._placeholder_shown:
                self.text.config(fg=th.MUTED)
            else:
                self.text.config(fg=th.TEXT)
        register_theme_callback(_on_text_theme_change)

        # Placeholder 效果
        self._placeholder_shown = True
        self._placeholder_text = "在此粘贴或输入待分析文本……支持中文、英文及混合文本"
        self.text.insert("end", self._placeholder_text)
        self.text.config(fg=t.MUTED)
        self.text.bind("<FocusIn>", self._on_text_focus_in)
        self.text.bind("<FocusOut>", self._on_text_focus_out)

        # 右面板：标签页
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True, padx=(6, 0))

        nb = ttk.Notebook(right)
        nb.pack(fill="both", expand=True)

        self.basic_tab = BasicTab(nb, self)
        self.syntax_tab = SyntaxTab(nb, self)
        self.compare_tab = CompareTab(nb, self)
        self.viz_tab = VizTab(nb, self)
        self.history_tab = HistoryTab(nb, self)
        self.fingerprint_tab = FingerprintTab(nb, self)

        nb.add(self.basic_tab, text="  📊 基础分析  ")
        nb.add(self.syntax_tab, text="  🔍 句法/语义  ")
        nb.add(self.compare_tab, text="  ⚖ 对比分析  ")
        nb.add(self.viz_tab, text="  📈 可视化  ")
        nb.add(self.history_tab, text="  📜 历史记录  ")
        nb.add(self.fingerprint_tab, text="  🔬 语言指纹  ")

    def _on_text_focus_in(self, event) -> None:
        if self._placeholder_shown:
            self.text.delete("1.0", "end")
            self.text.config(fg=get_theme().TEXT)
            self._placeholder_shown = False

    def _on_text_focus_out(self, event) -> None:
        if not self.text.get("1.0", "end-1c").strip():
            self._placeholder_shown = True
            t = get_theme()
            self.text.insert("end", self._placeholder_text)
            self.text.config(fg=t.MUTED)

    # ----------------------------------------------------------------- #
    # 状态栏
    # ----------------------------------------------------------------- #

    def _build_statusbar(self) -> None:
        t = get_theme()
        self._status = tk.Label(
            self.root,
            text="就绪  —  输入文本后点击分析按钮开始",
            font=(FONT, 9), bg=t.ROW_ALT, fg=t.MUTED,
            anchor="w", padx=14, pady=5,
        )
        self._status.pack(fill="x", side="bottom")
        self._theme_widgets.append(self._status)

    def set_status(self, msg: str) -> None:
        if hasattr(self, '_status'):
            self._status.config(text=msg)

    # ----------------------------------------------------------------- #
    # 状态提示
    # ----------------------------------------------------------------- #

    def _show_status_hint(self) -> None:
        st = analyzer.selfcheck()
        missing = [k for k, v in st.items() if not v]
        if not missing:
            return
        names = {
            "spacy_zh": "spaCy 中文模型 (zh_core_web_sm)",
            "nltk": "NLTK / VADER 英文情感",
        }
        friendly = [names.get(k, k) for k in missing]
        self.root.after(
            300,
            lambda: messagebox.showinfo(
                "后端提示",
                "以下可选后端未安装，相关功能将自动降级：\n"
                + "\n".join(f"  ✗ {n}" for n in friendly)
                + "\n\n不影响基本使用。完整安装请见 README。",
            ),
        )

    # ----------------------------------------------------------------- #
    # 提供给 Tab 的接口
    # ----------------------------------------------------------------- #

    def get_text(self) -> str:
        if self._placeholder_shown:
            return ""
        return self.text.get("1.0", "end-1c")

    def get_lang(self):
        m = {"自动": None, "中文": "zh", "英文": "en", "中英混合": "mixed"}
        return m.get(self.lang_var.get())

    # ----------------------------------------------------------------- #
    # 菜单动作
    # ----------------------------------------------------------------- #

    def open_file(self) -> None:
        path = filedialog.askopenfilename(filetypes=file_io.FILETYPES)
        if not path:
            return
        try:
            content = file_io.read_file(path)
            self.text.delete("1.0", "end")
            self.text.insert("end", content)
            self.text.config(fg=get_theme().TEXT)
            self._placeholder_shown = False
            count = len(content.replace(" ", "").replace("\n", "").replace("\r", ""))
            self.set_status(f"已打开: {path}  ({count:,} 字符)")
        except Exception as e:
            messagebox.showerror("错误", f"无法读取文件：{e}")

    def save_file(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".txt", filetypes=[("文本文件", "*.txt")]
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.get_text())
        self.set_status(f"已保存: {path}")

    def clear_text(self) -> None:
        self.text.delete("1.0", "end")
        t = get_theme()
        self.text.insert("end", self._placeholder_text)
        self.text.config(fg=t.MUTED)
        self._placeholder_shown = True
        self.set_status("已清空输入")

    def load_sample(self) -> None:
        sample = (
            "自然语言处理是人工智能的重要分支。它让计算机能够理解人类语言。\n"
            "近年来，深度学习大幅推动了该领域的发展。然而挑战依然存在。\n\n"
            "苹果公司总部位于美国加利福尼亚州的库比蒂诺，由蒂姆·库克担任首席执行官。"
            "这家公司在全球拥有数十亿用户。\n\n"
            "Apple Inc. is headquartered in Cupertino, California. "
            "Tim Cook is the CEO of the tech giant. "
            "Natural language processing is a fascinating field. "
            "It enables computers to understand human language. "
            "Deep learning has greatly advanced this area, but challenges remain."
        )
        self.text.delete("1.0", "end")
        self.text.insert("end", sample)
        self.text.config(fg=get_theme().TEXT)
        self._placeholder_shown = False
        self.set_status("已加载示例文本")

    def open_api_settings(self) -> None:
        t = get_theme()
        dlg = tk.Toplevel(self.root)
        dlg.title("API 配置")
        dlg.geometry("480x300")
        dlg.configure(bg=t.CARD)
        dlg.grab_set()
        dlg.transient(self.root)

        cfg = api_backend.load_config()

        # 标题
        tk.Label(dlg, text="🔌 API 配置", bg=t.CARD, fg=t.TEXT,
                 font=(FONT, 13, "bold")).pack(anchor="w", padx=16, pady=(14, 10))

        tk.Label(dlg, text="Base URL（OpenAI 兼容）", bg=t.CARD, fg=t.TEXT,
                 font=(FONT, 10)).pack(anchor="w", padx=16, pady=(0, 0))
        base = tk.Entry(dlg, width=52, font=(FONT_MONO, 10), relief="solid", borderwidth=1,
                        bg=t.INPUT_BG, fg=t.INPUT_FG,
                        highlightthickness=1, highlightcolor=t.ACCENT, highlightbackground=t.BORDER)
        base.insert(0, cfg.get("base_url", "https://api.openai.com/v1"))
        base.pack(padx=16, pady=(3, 0), fill="x")

        tk.Label(dlg, text="API Key", bg=t.CARD, fg=t.TEXT,
                 font=(FONT, 10)).pack(anchor="w", padx=16, pady=(10, 0))
        key = tk.Entry(dlg, width=52, show="*", font=(FONT_MONO, 10), relief="solid", borderwidth=1,
                       bg=t.INPUT_BG, fg=t.INPUT_FG,
                       highlightthickness=1, highlightcolor=t.ACCENT, highlightbackground=t.BORDER)
        key.insert(0, cfg.get("api_key", ""))
        key.pack(padx=16, pady=(3, 0), fill="x")

        tk.Label(dlg, text="模型名称", bg=t.CARD, fg=t.TEXT,
                 font=(FONT, 10)).pack(anchor="w", padx=16, pady=(10, 0))
        model = tk.Entry(dlg, width=52, font=(FONT_MONO, 10), relief="solid", borderwidth=1,
                         bg=t.INPUT_BG, fg=t.INPUT_FG,
                         highlightthickness=1, highlightcolor=t.ACCENT, highlightbackground=t.BORDER)
        model.insert(0, cfg.get("model", "claude-fable-5"))
        model.pack(padx=16, pady=(3, 0), fill="x")

        def save():
            api_backend.save_config(
                {
                    "base_url": base.get().strip(),
                    "api_key": key.get().strip(),
                    "model": model.get().strip(),
                }
            )
            messagebox.showinfo("已保存", "API 配置已保存。", parent=dlg)
            dlg.destroy()
            self.set_status("API 配置已更新")

        btn_frame = tk.Frame(dlg, bg=t.CARD)
        btn_frame.pack(fill="x", padx=16, pady=18)

        tk.Button(
            btn_frame, text="取消",
            bg=t.BUTTON_BG, fg=t.TEXT, font=(FONT, 10),
            relief="flat", padx=20, pady=7,
            activebackground=t.BUTTON_HOVER,
            command=dlg.destroy,
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            btn_frame, text="💾 保存",
            bg=t.ACCENT, fg="#ffffff", font=(FONT, 10, "bold"),
            relief="flat", padx=20, pady=7,
            activebackground=t.ACCENT_HOVER,
            command=save,
        ).pack(side="right")

    def show_backend_status(self) -> None:
        st = analyzer.selfcheck()
        names = {
            "jieba": "jieba 中文分词",
            "spacy_en": "spaCy 英文模型 (en_core_web_sm)",
            "spacy_zh": "spaCy 中文模型 (zh_core_web_sm)",
            "snownlp": "SnowNLP 中文情感",
            "nltk": "NLTK / VADER 英文情感",
            "wordcloud": "wordcloud 词云",
            "matplotlib": "matplotlib 绘图",
        }
        lines = [
            f"{names.get(k, k):40s} {'✓' if v else '✗'}"
            for k, v in sorted(st.items())
        ]
        messagebox.showinfo("后端状态", "\n".join(lines))

    def about(self) -> None:
        messagebox.showinfo(
            "关于",
            "📝 汉英 NLP 分析工具  V1.0\n"
            "Python + Tkinter · 本地与云端混合\n\n"
            "作者：Fragesius\n"
            "联系方式：fragesius@gmail.com\n\n"
            "本地引擎：jieba + spaCy + SnowNLP\n"
            "可选 AI：任意 OpenAI 兼容 API\n"
            "绘图：matplotlib + wordcloud\n\n"
            "支持深色/浅色主题切换",
        )


def show_first_run_setup(parent: tk.Tk) -> None:
    """首次运行向导：引导用户配置 API 密钥。

    用户可选择：
    - 立即配置 API（打开设置对话框）
    - 跳过，仅使用本地分析功能
    - 下次不再提示
    """
    from core._paths import mark_setup_done
    from ui.style import get_theme as _t

    t = _t()
    dlg = tk.Toplevel(parent)
    dlg.title("欢迎使用")
    dlg.geometry("560x380")
    dlg.configure(bg=t.CARD)
    dlg.grab_set()
    dlg.transient(parent)
    # 居中
    dlg.update_idletasks()
    pw, ph = parent.winfo_width(), parent.winfo_height()
    px, py = parent.winfo_x(), parent.winfo_y()
    dw, dh = 560, 380
    dlg.geometry(f"{dw}x{dh}+{px + (pw - dw) // 2}+{py + (ph - dh) // 2}")

    skip = tk.BooleanVar(value=False)

    # ── 标题区 ──
    tk.Label(
        dlg, text="📝 欢迎使用汉英 NLP 分析工具",
        bg=t.CARD, fg=t.TEXT,
        font=(FONT, 15, "bold"),
    ).pack(anchor="w", padx=24, pady=(20, 6))

    tk.Label(
        dlg,
        text="本地优先 · 离线可用 · 可选 AI 增强",
        bg=t.CARD, fg=t.MUTED,
        font=(FONT, 10),
    ).pack(anchor="w", padx=24)

    # ── 说明区 ──
    info_frame = tk.Frame(dlg, bg=t.CARD)
    info_frame.pack(fill="x", padx=24, pady=(18, 12))

    lines = [
        ("✅", "本地分析引擎 100% 离线可用，无需任何配置"),
        ("🔍", "中文分词、命名实体识别、关键词提取、情感分析"),
        ("🤖", "如需 AI 高级分析，可配置 OpenAI 兼容 API（如 DeepSeek）"),
        ("🔒", "API 密钥仅存储在本地 _data/ 文件夹中，不会上传"),
    ]
    for icon, text in lines:
        row = tk.Frame(info_frame, bg=t.CARD)
        row.pack(fill="x", pady=3)
        tk.Label(row, text=icon, bg=t.CARD, font=(FONT, 11)).pack(side="left")
        tk.Label(
            row, text=text, bg=t.CARD, fg=t.TEXT,
            font=(FONT, 10), anchor="w",
        ).pack(side="left", padx=(8, 0))

    # ── 提示 ──
    tip = tk.Label(
        dlg,
        text="💡 可稍后在「设置 → API 配置」中随时配置。",
        bg=t.CARD, fg=get_theme().MUTED,
        font=(FONT, 9),
    )
    tip.pack(anchor="w", padx=24, pady=(0, 4))

    # ── 结果标记 ──
    result = {"configured": False}

    def _do_configure():
        """打开 API 设置对话框。"""
        dlg.withdraw()  # 隐藏欢迎窗
        parent.update_idletasks()
        # 复用 App 的 open_api_settings；需要在 app 实例上调用
        app = getattr(parent, "_app_instance", None)
        if app:
            app.open_api_settings()
        result["configured"] = True
        _finish()

    def _do_skip():
        result["configured"] = False
        _finish()

    def _finish():
        if skip.get():
            mark_setup_done()
        dlg.destroy()

    # ── 按钮区 ──
    btn_frame = tk.Frame(dlg, bg=t.CARD)
    btn_frame.pack(fill="x", padx=24, pady=(8, 18))

    # 跳过按钮（次要）
    tk.Button(
        btn_frame, text="跳过，使用本地分析  →",
        bg=t.BUTTON_BG, fg=t.TEXT, font=(FONT, 10),
        relief="flat", padx=18, pady=8,
        activebackground=t.BUTTON_HOVER,
        command=_do_skip,
    ).pack(side="right", padx=(8, 0))

    # 配置按钮（主要）
    tk.Button(
        btn_frame, text="🔌 配置 API 密钥",
        bg=t.ACCENT, fg="#ffffff", font=(FONT, 10, "bold"),
        relief="flat", padx=18, pady=8,
        activebackground=t.ACCENT_HOVER,
        command=_do_configure,
    ).pack(side="right")

    # "不再提示" 复选框
    cb_frame = tk.Frame(dlg, bg=t.CARD)
    cb_frame.pack(fill="x", padx=24, pady=(0, 20))
    tk.Checkbutton(
        cb_frame,
        text="下次不再显示此向导（可在设置中重新配置 API）",
        variable=skip,
        bg=t.CARD, fg=t.MUTED,
        selectcolor=t.INPUT_BG,
        activebackground=t.CARD,
        font=(FONT, 9),
    ).pack(side="left")

    # 等待对话框关闭
    parent.wait_window(dlg)
    return result["configured"]


def main() -> None:
    from ui.style import set_theme, detect_system_dark_mode

    enable_dpi_awareness()
    root = tk.Tk()

    # 跟随系统深色/浅色模式自动切换
    if detect_system_dark_mode():
        set_theme(root, "dark")

    app = App(root)
    # 注册以便 setup 对话框能调用 app.open_api_settings()
    root._app_instance = app

    # 根据实际主题调整按钮文字
    from ui.style import get_theme
    if get_theme().name == "dark":
        app.theme_btn.config(text="☀ 浅色模式", bg=get_theme().ACCENT_SOFT,
                             fg=get_theme().ACCENT,
                             activebackground=get_theme().ACCENT,
                             activeforeground="#ffffff")

    # ── 首次运行向导 ──
    from core._paths import is_first_run
    from core import api_backend

    if is_first_run() and not api_backend.is_configured():
        # 延迟弹出，等主窗口先渲染
        root.after(400, lambda: show_first_run_setup(root))

    root.mainloop()


if __name__ == "__main__":
    main()
