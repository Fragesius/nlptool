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
    get_responsive_window_size,
    get_responsive_min_size,
    is_compact_mode,
    responsive_padding,
    responsive_font_size,
    FONT,
    FONT_MONO,
    FONT_SCALE,
)
from ui.tabs import BasicTab, SyntaxTab, CompareTab, VizTab, HistoryTab, FingerprintTab, BatchTab, ExperimentTab

import ui.style as s


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("汉英 NLP 分析工具")

        # 响应式窗口尺寸
        w, h = get_responsive_window_size()
        min_w, min_h = get_responsive_min_size()
        root.geometry(f"{w}x{h}")
        root.minsize(min_w, min_h)
        root.configure(bg=s.BG)

        self._compact = is_compact_mode()

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

        # 顶部强调色条
        top_accent = tk.Frame(self.root, bg=t.ACCENT, height=3)
        top_accent.pack(fill="x")
        self._top_accent = top_accent

        bar = tk.Frame(
            self.root, bg=t.CARD,
            highlightthickness=0,
        )
        bar.pack(fill="x")
        bar._is_card = True

        # 底部阴影线
        shadow = tk.Frame(self.root, bg=t.BORDER, height=1)
        shadow.pack(fill="x")
        self._shadow = shadow  # 跟踪用于主题切换

        inner = tk.Frame(bar, bg=t.CARD)
        inner._is_card = True
        header_padx = responsive_padding(24)
        header_pady = (responsive_padding(14), responsive_padding(10))
        inner.pack(fill="x", padx=header_padx, pady=header_pady)

        # 左侧：标题与副标题
        left = tk.Frame(inner, bg=t.CARD)
        left._is_card = True
        left.pack(side="left")

        tk.Label(
            left, text="📝 汉英 NLP 分析工具",
            font=(FONT, responsive_font_size(FONT_SCALE["title"]), "bold")
            if not self._compact else (FONT, responsive_font_size(FONT_SCALE["title2"]), "bold"),
            bg=t.CARD, fg=t.TEXT,
        ).pack(side="left")

        self.subtitle_label = tk.Label(
            left, text="汉语 · 英语 · 本地优先 · 可选 AI",
            font=(FONT, responsive_font_size(FONT_SCALE["footnote"])),
            bg=t.CARD, fg=t.MUTED,
        )
        if not self._compact:
            self.subtitle_label.pack(side="left", padx=(10, 0))
        # 紧凑模式: 不显示副标题

        # 右侧：后端状态 + 主题切换
        right = tk.Frame(inner, bg=t.CARD)
        right._is_card = True
        right.pack(side="right")

        self.backend_indicator = tk.Label(
            right, text="",
            font=(FONT, responsive_font_size(FONT_SCALE["footnote"])),
            bg=t.ACCENT_SOFT, fg=t.SUCCESS,
            padx=10, pady=2,
        )
        self.backend_indicator.pack(side="left", padx=(0, 12))
        self._update_backend_indicator()

        # 主题切换按钮（圆角药丸风格，tk.Button 确保文字在所有系统上可见）
        self.theme_btn = tk.Button(
            right,
            text="☾ 深色模式",
            font=(FONT, responsive_font_size(FONT_SCALE["footnote"])),
            bg=t.ACCENT, fg="#ffffff",
            relief="flat", padx=14, pady=4,
            activebackground=t.ACCENT_HOVER, activeforeground="#ffffff",
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
            self.theme_btn.config(text="☀ 浅色模式", bg=t.ACCENT, fg="#ffffff",
                                  activebackground=t.ACCENT_HOVER, activeforeground="#ffffff")
        else:
            self.theme_btn.config(text="☾ 深色模式", bg=t.ACCENT, fg="#ffffff",
                                  activebackground=t.ACCENT_HOVER, activeforeground="#ffffff")
        self._apply_theme_to_tk_widgets()

    def _apply_theme_to_tk_widgets(self) -> None:
        """手动更新所有已记录的 tk 组件颜色（ttk 组件已由 apply_style 处理）。"""
        t = get_theme()
        for w in self._theme_widgets:
            try:
                if isinstance(w, tk.Frame) or isinstance(w, tk.Toplevel):
                    w.configure(bg=t.CARD if hasattr(w, '_is_card') else t.BG)
                elif isinstance(w, tk.Label):
                    # 后端状态指示器保持药丸底色
                    if w is getattr(self, 'backend_indicator', None):
                        w.configure(bg=t.ACCENT_SOFT, fg=t.SUCCESS)
                    else:
                        w.configure(bg=t.CARD if w.master and getattr(w.master, '_is_card', False) else t.BG)
                elif isinstance(w, tk.Text):
                    w.configure(bg=t.INPUT_BG, fg=t.INPUT_FG,
                                highlightbackground=t.BORDER,
                                selectbackground=t.SELECT_BG)
            except Exception:
                pass
        # 更新顶部强调色条
        if hasattr(self, '_top_accent'):
            self._top_accent.configure(bg=t.ACCENT)
        # 更新阴影线
        if hasattr(self, '_shadow'):
            self._shadow.configure(bg=t.BORDER)
        # 更新主题按钮（保持填充主色）
        if hasattr(self, 'theme_btn'):
            self.theme_btn.configure(bg=t.ACCENT, fg="#ffffff",
                                     activebackground=t.ACCENT_HOVER)
        # 更新菜单
        self._rebuild_menu_colors()
        # 更新状态栏
        if hasattr(self, '_status_top_line'):
            self._status_top_line.configure(bg=t.BORDER)
        if hasattr(self, '_status'):
            self._status.configure(bg=t.CARD, fg=t.MUTED)

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
        # 全局快捷键只绑定一次，避免主题切换时累积
        self.root.bind("<Control-o>", lambda e: self.open_file())
        self.root.bind("<Control-s>", lambda e: self.save_file())

    def _rebuild_menu_colors(self) -> None:
        t = get_theme()
        menu_font = (FONT, responsive_font_size(FONT_SCALE["body"]))
        menubar = tk.Menu(self.root, bg=t.CARD, fg=t.TEXT,
                          activebackground=t.ACCENT_SOFT, activeforeground=t.TEXT,
                          borderwidth=0, font=menu_font)

        mfile = tk.Menu(menubar, tearoff=0, bg=t.CARD, fg=t.TEXT,
                        activebackground=t.ACCENT_SOFT, activeforeground=t.TEXT,
                        font=menu_font)
        mfile.add_command(label="📂 打开文件…", command=self.open_file, accelerator="Ctrl+O")
        mfile.add_command(label="💾 保存结果…", command=self.save_file, accelerator="Ctrl+S")
        mfile.add_separator()
        mfile.add_command(label="退出", command=self.root.quit)
        menubar.add_cascade(label="文件", menu=mfile)

        mset = tk.Menu(menubar, tearoff=0, bg=t.CARD, fg=t.TEXT,
                       activebackground=t.ACCENT_SOFT, activeforeground=t.TEXT,
                       font=menu_font)
        mset.add_command(label="🔌 API 配置…", command=self.open_api_settings)
        mset.add_command(label="📋 检查后端状态", command=self.show_backend_status)
        mset.add_separator()
        theme_label = "☀️ 切换到浅色模式" if t.name == "dark" else "🌙 切换到深色模式"
        mset.add_command(label=theme_label, command=self._toggle_theme)
        menubar.add_cascade(label="设置", menu=mset)

        mhelp = tk.Menu(menubar, tearoff=0, bg=t.CARD, fg=t.TEXT,
                        activebackground=t.ACCENT_SOFT, activeforeground=t.TEXT,
                        font=menu_font)
        mhelp.add_command(label="关于", command=self.about)
        menubar.add_cascade(label="帮助", menu=mhelp)

        self.root.config(menu=menubar)
        # 快捷键只绑定一次，不在主题重建时重复绑定

    # ----------------------------------------------------------------- #
    # 主体
    # ----------------------------------------------------------------- #

    def _build_body(self) -> None:
        body_padx = responsive_padding(12)
        body_pady = (responsive_padding(8), responsive_padding(4))
        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True, padx=body_padx, pady=body_pady)

        # ── 左右分栏 PanedWindow（用户可拖动分隔条）──
        pane = ttk.PanedWindow(body, orient="horizontal")
        pane.pack(fill="both", expand=True)

        # 左面板：输入
        left = ttk.LabelFrame(pane, text="📥 输入文本", style="Card.TLabelframe")

        ctrl = ttk.Frame(left)
        ctrl.pack(fill="x", padx=12, pady=(12, 4))
        ttk.Label(ctrl, text="检测语言：", font=(FONT, responsive_font_size(FONT_SCALE["body"]))).pack(side="left")
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
            left, wrap="word", font=(FONT_MONO, responsive_font_size(FONT_SCALE["headline"])),
            bg=t.INPUT_BG, fg=t.TEXT,
            highlightthickness=1, highlightbackground=t.BORDER,
            highlightcolor=t.ACCENT,
            selectbackground=t.SELECT_BG, selectforeground=t.TEXT,
            insertbackground=t.TEXT,
        )
        self.text.pack(fill="both", expand=True, padx=12, pady=(4, 6))

        # 输入区底部提示
        self._input_hint = tk.Label(
            left,
            text="支持 txt / docx / pdf / html / md / rtf 等格式，可拖放或从菜单打开",
            font=(FONT, responsive_font_size(FONT_SCALE["caption"])),
            bg=t.CARD, fg=t.MUTED,
            anchor="w",
        )
        self._input_hint.pack(fill="x", padx=12, pady=(0, 8))

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
            self._input_hint.config(bg=th.CARD, fg=th.MUTED)
        register_theme_callback(_on_text_theme_change)

        # Placeholder 效果
        self._placeholder_shown = True
        self._placeholder_text = "在此粘贴或输入待分析文本……\n支持中文、英文及混合文本，也可从菜单「文件 → 打开」导入文档"
        self.text.insert("end", self._placeholder_text)
        self.text.config(fg=t.MUTED)
        self.text.bind("<FocusIn>", self._on_text_focus_in)
        self.text.bind("<FocusOut>", self._on_text_focus_out)

        # 右面板：标签页
        right = ttk.Frame(pane)

        # 添加到 PanedWindow（比例可调）
        pane.add(left, weight=42)   # 左面板 42% 初始宽度
        pane.add(right, weight=58)  # 右面板 58% 初始宽度

        nb = ttk.Notebook(right)
        nb.pack(fill="both", expand=True)

        self.basic_tab = BasicTab(nb, self)
        self.syntax_tab = SyntaxTab(nb, self)
        self.compare_tab = CompareTab(nb, self)
        self.viz_tab = VizTab(nb, self)
        self.batch_tab = BatchTab(nb, self)
        self.history_tab = HistoryTab(nb, self)
        self.fingerprint_tab = FingerprintTab(nb, self)
        self.experiment_tab = ExperimentTab(nb, self)

        # ── Notebook 标签：紧凑模式下缩短文字 ──
        if self._compact:
            nb.add(self.basic_tab, text="  📊 基础  ")
            nb.add(self.syntax_tab, text="  🔍 句法  ")
            nb.add(self.compare_tab, text="  ⚖ 对比  ")
            nb.add(self.viz_tab, text="  📈 可视化  ")
            nb.add(self.batch_tab, text="  📁 批量  ")
            nb.add(self.history_tab, text="  📜 历史  ")
            nb.add(self.fingerprint_tab, text="  🔬 指纹  ")
            nb.add(self.experiment_tab, text="  🧪 实验  ")
        else:
            nb.add(self.basic_tab, text="  📊 基础分析  ")
            nb.add(self.syntax_tab, text="  🔍 句法/语义  ")
            nb.add(self.compare_tab, text="  ⚖ 对比分析  ")
            nb.add(self.viz_tab, text="  📈 可视化  ")
            nb.add(self.batch_tab, text="  📁 批量处理  ")
            nb.add(self.history_tab, text="  📜 历史记录  ")
            nb.add(self.fingerprint_tab, text="  🔬 语言指纹  ")
            nb.add(self.experiment_tab, text="  🧪 批量实验  ")

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

        # 状态栏顶部细线
        self._status_top_line = tk.Frame(self.root, bg=t.BORDER, height=1)
        self._status_top_line.pack(fill="x", side="bottom")

        self._status = tk.Label(
            self.root,
            text="就绪  —  输入文本后点击分析按钮开始",
            font=(FONT, responsive_font_size(FONT_SCALE["footnote"])),
            bg=t.CARD, fg=t.MUTED,
            anchor="w", padx=16, pady=8,
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
        """获取输入文本，自动过滤掉句子序号标记。

        标记格式为 ``\\x00[序号]\\x00``（用 NULL 字符包裹），
        插入时带 ``elide=True`` 的 tag 让其不可见、不可选中，
        但 ``get()`` 仍会返回原始字符，因此这里用正则清除。
        """
        if self._placeholder_shown:
            return ""
        raw = self.text.get("1.0", "end-1c")
        # 过滤句子序号标记（\x00 包裹的 [n]）
        import re as _re
        return _re.sub(r"\x00\[\d+\]\x00", "", raw)

    def get_lang(self):
        m = {"自动": None, "中文": "zh", "英文": "en", "中英混合": "mixed"}
        return m.get(self.lang_var.get())

    # 句子标记用的 NULL 字符 sentinel（不会出现在正常文本中）
    _SENT_MARK_SENTINEL = "\x00"
    _SENT_MARK_RE = None  # 延迟编译

    def annotate_sentences(self, count: int) -> None:
        """分析完成后在句末插入不可见、不可选中的上标序号标记 ``[1] [2]``。

        实现要点：
        1. 标记用 ``\\x00[序号]\\x00`` 格式，用 NULL 字符包裹
           （正常文本不会包含 NULL，避免与正文冲突）。
        2. 标记带 ``elide=True`` 的 tag，Tk 会隐藏这些字符：
           - 视觉上不显示（不污染文本外观）
           - 用户无法用鼠标选中（select 不会包含 elide 文本）
           - 复制时不会包含（Tk 的 elide 文本默认不参与复制）
        3. ``get_text()`` 仍会返回原始字符（包括 NULL 标记），所以那里用正则过滤。
        4. 点击标记区域 → 通过 ``index @x,y`` 定位 → 向后搜索 ``\\x00[\\d+]\\x00``
           提取序号 → 展开对应句子卡片。
        5. 用户修改文本（``<<Modified>>`` 事件）→ 自动清除所有标记。
        """
        if self._placeholder_shown or count <= 0:
            return

        # 先清除旧标记（真正删除字符，而非只删 tag）
        self.clear_sentence_marks()

        content = self.text.get("1.0", "end-1c")

        # 配置 elide tag（隐藏文本，Tk 8.5+ 支持）
        self.text.tag_configure(
            "sent_marker",
            elide=True,
            foreground="#007AFF",
            background="#e8f0ff",
            font=(FONT, responsive_font_size(FONT_SCALE["footnote"]) - 1, "bold"),
        )
        # 配置上标可见 tag（仅用于显示，实际仍用 elide 隐藏）
        # 这里选择完全 elide 隐藏，保持文本干净

        # 在句末标点后插入 [1] [2] ...
        import re
        sent_ends = list(re.finditer(r"[。！？!?\.](?=\s|$|\n)", content))
        n_found = min(len(sent_ends), count)

        # 从后往前插入，避免偏移
        for i in range(n_found - 1, -1, -1):
            end = sent_ends[i].end()
            # 用 NULL 包裹，便于过滤和解析
            marker = f"{self._SENT_MARK_SENTINEL}[{i + 1}]{self._SENT_MARK_SENTINEL}"
            line_col = self.text.index(f"1.0+{end}c")
            self.text.insert(line_col, marker, ("sent_marker",))

        # 点击标记区域 → 定位并展开对应句子卡片
        def _on_click(event):
            try:
                idx = self.text.index(f"@{event.x},{event.y}")
                # 在点击位置附近搜索 NULL 标记
                start = self.text.index(f"{idx} - 8c")
                end = self.text.index(f"{idx} + 8c")
                nearby = self.text.get(start, end)
                m = re.search(r"\x00\[(\d+)\]\x00", nearby)
                if m:
                    si = int(m.group(1)) - 1
                    self.syntax_tab.show_sentence(si)
            except Exception:
                pass

        self.text.tag_bind("sent_marker", "<Button-1>", _on_click)

        # 监听文本修改：用户编辑后自动清除标记
        if not getattr(self, "_mark_modified_bound", False):
            def _on_modified(_event):
                # <<Modified>> 会在文本变化时触发，清除标记并重置标志
                # 避免在清除标记的过程中递归触发
                if self.text.edit_modified() and not getattr(self, "_clearing_marks", False):
                    self._clearing_marks = True
                    try:
                        self.clear_sentence_marks()
                    finally:
                        self._clearing_marks = False
                        self.text.edit_modified(False)
            self.text.bind("<<Modified>>", _on_modified)
            self._mark_modified_bound = True

    def clear_sentence_marks(self) -> None:
        """删除所有句子序号标记（真正从文本中移除字符）。

        性能优化：用 re.finditer 批量查找所有标记位置，从后往前一次性删除，
        避免 O(n²) 的 while True 循环。
        """
        import re
        self._clearing_marks = True
        try:
            content = self.text.get("1.0", "end-1c")
            # 批量查找所有标记，从后往前删除避免偏移
            matches = list(re.finditer(r"\x00\[\d+\]\x00", content))
            for m in reversed(matches):
                start = self.text.index(f"1.0+{m.start()}c")
                end = self.text.index(f"1.0+{m.end()}c")
                self.text.delete(start, end)
            self.text.tag_delete("sent_marker")
            self.text.edit_modified(False)
            # 视觉反馈：状态栏提示
            self.set_status("句法标记已清除")
        finally:
            self._clearing_marks = False

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
                 font=(FONT, responsive_font_size(FONT_SCALE["title2"]), "bold")
                 ).pack(anchor="w", padx=16, pady=(14, 10))

        tk.Label(dlg, text="Base URL（OpenAI 兼容）", bg=t.CARD, fg=t.TEXT,
                 font=(FONT, responsive_font_size(FONT_SCALE["body"]))
                 ).pack(anchor="w", padx=16, pady=(0, 0))
        base = tk.Entry(dlg, width=52, font=(FONT_MONO, responsive_font_size(FONT_SCALE["body"])),
                        bg=t.INPUT_BG, fg=t.INPUT_FG,
                        highlightthickness=1, highlightcolor=t.ACCENT, highlightbackground=t.BORDER)
        base.insert(0, cfg.get("base_url", "https://api.openai.com/v1"))
        base.pack(padx=16, pady=(3, 0), fill="x")

        tk.Label(dlg, text="API Key", bg=t.CARD, fg=t.TEXT,
                 font=(FONT, responsive_font_size(FONT_SCALE["body"]))).pack(anchor="w", padx=16, pady=(10, 0))
        key = tk.Entry(dlg, width=52, show="*", font=(FONT_MONO, responsive_font_size(FONT_SCALE["body"])), relief="solid", borderwidth=1,
                       bg=t.INPUT_BG, fg=t.INPUT_FG,
                       highlightthickness=1, highlightcolor=t.ACCENT, highlightbackground=t.BORDER)
        key.insert(0, cfg.get("api_key", ""))
        key.pack(padx=16, pady=(3, 0), fill="x")

        tk.Label(dlg, text="模型名称", bg=t.CARD, fg=t.TEXT,
                 font=(FONT, responsive_font_size(FONT_SCALE["body"]))).pack(anchor="w", padx=16, pady=(10, 0))
        model = tk.Entry(dlg, width=52, font=(FONT_MONO, responsive_font_size(FONT_SCALE["body"])), relief="solid", borderwidth=1,
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
            bg=t.BUTTON_BG, fg=t.TEXT,
            font=(FONT, responsive_font_size(FONT_SCALE["body"])),
            relief="flat", padx=20, pady=7,
            activebackground=t.BUTTON_HOVER,
            command=dlg.destroy,
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            btn_frame, text="💾 保存",
            bg=t.ACCENT, fg="#ffffff",
            font=(FONT, responsive_font_size(FONT_SCALE["body"]), "bold"),
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
            "📝 汉英 NLP 分析工具  V1.2.0\n"
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
    """
    from core._paths import mark_setup_done
    from ui.style import get_theme as _t, get_screen_size, is_compact_mode

    t = _t()
    dlg = tk.Toplevel(parent)
    dlg.title("欢迎使用")
    dlg.configure(bg=t.CARD)
    dlg.grab_set()
    dlg.transient(parent)

    # ── 响应式尺寸：确保所有内容可见 ──
    _, sh = get_screen_size()
    if sh <= 720:
        dw, dh = 660, 580
    elif sh <= 768:
        dw, dh = 740, 640
    elif sh <= 900:
        dw, dh = 800, 700
    elif sh <= 1080:
        dw, dh = 860, 760
    else:
        dw, dh = 920, 820
    dlg.minsize(560, 480)

    # 居中
    dlg.update_idletasks()
    pw, ph = parent.winfo_width(), parent.winfo_height()
    px, py = parent.winfo_x(), parent.winfo_y()
    dlg.geometry(f"{dw}x{dh}+{px + (pw - dw) // 2}+{py + (ph - dh) // 2}")

    compact = is_compact_mode()
    tpad = 24 if not compact else 16          # 水平边距
    card_vpad = 3 if not compact else 2       # 卡片垂直间距
    card_ipadx = 12 if not compact else 10    # 卡片内部水平间距
    card_ipady = 9 if not compact else 7      # 卡片内部垂直间距

    skip = tk.BooleanVar(value=False)

    # ── Canvas + Scrollbar（仅极小屏幕启用滚动）──
    use_scroll = sh <= 720
    if use_scroll:
        canvas = tk.Canvas(dlg, bg=t.CARD, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(dlg, orient="vertical", command=canvas.yview)
        scrollable = tk.Frame(canvas, bg=t.CARD)
        canvas.create_window((0, 0), window=scrollable, anchor="nw", tags="inner")
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_canvas_resize(event):
            """让内部 frame 始终填满 Canvas 宽度。"""
            canvas.itemconfig("inner", width=event.width)

        def _on_content_resize(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            if scrollable.winfo_reqheight() > canvas.winfo_height():
                scrollbar.pack(side="right", fill="y")
            else:
                scrollbar.pack_forget()

        canvas.bind("<Configure>", _on_canvas_resize)
        scrollable.bind("<Configure>", _on_content_resize)
        canvas.pack(side="left", fill="both", expand=True)
    else:
        scrollable = tk.Frame(dlg, bg=t.CARD)
        scrollable.pack(fill="both", expand=True)

    # ═══════════════════════════════════════════════════════════════
    # 标题区
    # ═══════════════════════════════════════════════════════════════

    tk.Label(
        scrollable,
        text="欢迎使用汉英 NLP 分析工具",
        bg=t.CARD, fg=t.TEXT,
        font=(FONT, responsive_font_size(FONT_SCALE["largeTitle"]), "bold"),
    ).pack(anchor="w", padx=tpad, pady=(tpad, 4))

    tk.Label(
        scrollable,
        text="📝  本地优先 · 离线可用 · 可选 AI 增强",
        bg=t.CARD, fg=t.MUTED,
        font=(FONT, responsive_font_size(FONT_SCALE["callout"])),
    ).pack(anchor="w", padx=tpad)

    # ═══════════════════════════════════════════════════════════════
    # 功能卡片区
    # ═══════════════════════════════════════════════════════════════

    features = [
        ("✅", "纯本地引擎",
         "jieba + spaCy + SnowNLP，100% 离线可用，无需联网"),
        ("🔍", "深度文本分析",
         "分词·命名实体·关键词·情感·依存句法·可读性"),
        ("🤖", "可选 AI 增强",
         "配置 OpenAI 兼容 API，解锁高级语言学分析"),
        ("🔒", "数据完全本地",
         "API 密钥仅存 _data/ 文件夹，绝不离开本机"),
        ("🌓", "自动主题切换",
         "跟随系统深色/浅色模式，减少视觉疲劳"),
    ]

    # 功能卡片容器
    card_container = tk.Frame(scrollable, bg=t.CARD)
    card_container.pack(fill="x", padx=tpad, pady=(16, 8))

    for icon, title, desc in features:
        card = tk.Frame(card_container, bg=t.BG)
        card.pack(fill="x", pady=card_vpad)

        tk.Label(
            card, text=icon,
            bg=t.BG, fg=t.TEXT,
            font=(FONT, responsive_font_size(FONT_SCALE["title3"])),
        ).pack(side="left", padx=(card_ipadx, 10), pady=card_ipady)

        text_col = tk.Frame(card, bg=t.BG)
        text_col.pack(side="left", fill="x", expand=True, pady=card_ipady)

        tk.Label(
            text_col, text=title,
            bg=t.BG, fg=t.TEXT,
            font=(FONT, responsive_font_size(FONT_SCALE["headline"]), "bold"),
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            text_col, text=desc,
            bg=t.BG, fg=t.MUTED,
            font=(FONT, responsive_font_size(FONT_SCALE["footnote"])),
            anchor="w",
        ).pack(fill="x", pady=(1, 0))

    # ═══════════════════════════════════════════════════════════════
    # 提示
    # ═══════════════════════════════════════════════════════════════

    tk.Label(
        scrollable,
        text="💡 可稍后在菜单栏「设置 → API 配置」中随时修改。",
        bg=t.CARD, fg=t.MUTED,
        font=(FONT, responsive_font_size(FONT_SCALE["caption"])),
    ).pack(anchor="w", padx=tpad, pady=(0, 8))

    # ═══════════════════════════════════════════════════════════════
    # 分隔线
    # ═══════════════════════════════════════════════════════════════

    sep = tk.Frame(scrollable, bg=t.BORDER, height=1)
    sep.pack(fill="x", padx=tpad)

    # ═══════════════════════════════════════════════════════════════
    # 按钮区
    # ═══════════════════════════════════════════════════════════════

    result = {"configured": False}

    def _do_configure():
        """打开 API 设置对话框。"""
        dlg.withdraw()
        parent.update_idletasks()
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
    btn_frame = tk.Frame(scrollable, bg=t.CARD)
    btn_frame.pack(fill="x", padx=tpad, pady=(16, 0))

    # 主要操作（右）— Accent / Filled，加高确保不截断
    tk.Button(
        btn_frame, text="🔌 配置 API 密钥",
        bg=t.ACCENT, fg="#ffffff",
        font=(FONT, responsive_font_size(FONT_SCALE["body"]), "bold"),
        relief="flat", padx=24, pady=12,
        activebackground=t.ACCENT_HOVER,
        activeforeground="#ffffff",
        bd=0, cursor="hand2",
        command=_do_configure,
    ).pack(side="right")

    # 次要操作（左）— plain，与主按钮等高等宽
    tk.Button(
        btn_frame, text="跳过，使用本地分析",
        bg=t.CARD, fg=t.MUTED,
        font=(FONT, responsive_font_size(FONT_SCALE["body"])),
        relief="flat", padx=16, pady=12,
        activebackground=t.BUTTON_BG,
        activeforeground=t.TEXT,
        bd=0, cursor="hand2",
        command=_do_skip,
    ).pack(side="left")

    # ── "不再提示" ──
    cb_frame = tk.Frame(scrollable, bg=t.CARD)
    cb_frame.pack(fill="x", padx=tpad, pady=(12, tpad))

    tk.Checkbutton(
        cb_frame,
        text="下次不再显示此向导",
        variable=skip,
        bg=t.CARD, fg=t.MUTED,
        selectcolor=t.INPUT_BG,
        activebackground=t.CARD,
        font=(FONT, responsive_font_size(FONT_SCALE["footnote"])),
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
