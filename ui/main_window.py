"""主窗口（customtkinter）：输入区、语言选择、标签页、菜单、API 设置与主题切换。"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, filedialog

import customtkinter as ctk

from core import analyzer, api_backend, file_io
from ui import style as s
from ui.style import (
    enable_dpi_awareness,
    get_responsive_window_size,
    get_responsive_min_size,
    is_compact_mode,
    responsive_padding,
)
from ui.tabs import (
    BasicTab, SyntaxTab, CompareTab, VizTab,
    HistoryTab, FingerprintTab, BatchTab, ExperimentTab,
)


class App:
    def __init__(self, root: ctk.CTk):
        self.root = root
        root.title("汉英 NLP 分析工具")

        # 响应式窗口尺寸
        w, h = get_responsive_window_size()
        min_w, min_h = get_responsive_min_size()
        root.geometry(f"{w}x{h}")
        root.minsize(min_w, min_h)
        root.configure(fg_color=s.BG)

        self._compact = is_compact_mode()

        self._build_header()
        self._build_menu()
        self._build_body()
        self._build_statusbar()
        self._show_status_hint()

    # ----------------------------------------------------------------- #
    # 头部
    # ----------------------------------------------------------------- #

    def _build_header(self) -> None:
        # 顶部强调色条
        ctk.CTkFrame(self.root, fg_color=s.ACCENT, height=3,
                     corner_radius=0).pack(fill="x")

        bar = ctk.CTkFrame(self.root, fg_color=s.CARD, corner_radius=0)
        bar.pack(fill="x")

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        header_padx = responsive_padding(24)
        header_pady = (responsive_padding(12), responsive_padding(10))
        inner.pack(fill="x", padx=header_padx, pady=header_pady)

        # 左侧：标题与副标题
        left = ctk.CTkFrame(inner, fg_color="transparent")
        left.pack(side="left")

        ctk.CTkLabel(
            left, text="📝 汉英 NLP 分析工具",
            font=s.font("title" if not self._compact else "title2", bold=True),
        ).pack(side="left")

        if not self._compact:
            ctk.CTkLabel(
                left, text="汉语 · 英语 · 本地优先 · 可选 AI",
                font=s.font("footnote"), text_color=s.MUTED,
            ).pack(side="left", padx=(10, 0))

        # 右侧：后端状态 + 主题切换
        right = ctk.CTkFrame(inner, fg_color="transparent")
        right.pack(side="right")

        self.backend_indicator = ctk.CTkLabel(
            right, text="",
            font=s.font("footnote"),
            fg_color=s.ACCENT_SOFT, text_color=s.SUCCESS,
            corner_radius=10, padx=10, pady=3,
        )
        self.backend_indicator.pack(side="left", padx=(0, 12))
        self._update_backend_indicator()

        self.theme_btn = ctk.CTkButton(
            right,
            text="☀ 浅色模式" if s.is_dark() else "☾ 深色模式",
            font=s.font("footnote"),
            width=100, height=28,
            command=self._toggle_theme,
        )
        self.theme_btn.pack(side="left")

    def _toggle_theme(self) -> None:
        new_mode = s.toggle_appearance()
        self.theme_btn.configure(
            text="☀ 浅色模式" if new_mode == "dark" else "☾ 深色模式"
        )
        self._rebuild_menu()

    def _update_backend_indicator(self) -> None:
        st = analyzer.selfcheck()
        ok_count = sum(1 for v in st.values() if v)
        total = len(st)
        self.backend_indicator.configure(
            text=f"后端: {ok_count}/{total} 就绪" if ok_count < total else "✓ 全部后端就绪",
            text_color=s.SUCCESS if ok_count == total else s.MUTED,
        )

    # ----------------------------------------------------------------- #
    # 菜单（原生 tk.Menu：customtkinter 无菜单控件，系统菜单栏不渲染在窗口内）
    # ----------------------------------------------------------------- #

    def _build_menu(self) -> None:
        self._rebuild_menu()
        # 全局快捷键只绑定一次，避免主题切换时累积
        self.root.bind("<Control-o>", lambda e: self.open_file())
        self.root.bind("<Control-s>", lambda e: self.save_file())

    def _rebuild_menu(self) -> None:
        menu_bg = s.resolve(s.CARD)
        menu_fg = s.resolve(s.TEXT)
        active_bg = s.resolve(s.ACCENT_SOFT)
        menu_font = s.font("body")

        menubar = tk.Menu(self.root, bg=menu_bg, fg=menu_fg,
                          activebackground=active_bg, activeforeground=menu_fg,
                          borderwidth=0, font=menu_font)

        mfile = tk.Menu(menubar, tearoff=0, bg=menu_bg, fg=menu_fg,
                        activebackground=active_bg, activeforeground=menu_fg,
                        font=menu_font)
        mfile.add_command(label="📂 打开文件…", command=self.open_file, accelerator="Ctrl+O")
        mfile.add_command(label="💾 保存结果…", command=self.save_file, accelerator="Ctrl+S")
        mfile.add_separator()
        mfile.add_command(label="退出", command=self.root.quit)
        menubar.add_cascade(label="文件", menu=mfile)

        mset = tk.Menu(menubar, tearoff=0, bg=menu_bg, fg=menu_fg,
                       activebackground=active_bg, activeforeground=menu_fg,
                       font=menu_font)
        mset.add_command(label="🔌 API 配置…", command=self.open_api_settings)
        mset.add_command(label="📋 检查后端状态", command=self.show_backend_status)
        mset.add_separator()
        theme_label = "☀️ 切换到浅色模式" if s.is_dark() else "🌙 切换到深色模式"
        mset.add_command(label=theme_label, command=self._toggle_theme)
        menubar.add_cascade(label="设置", menu=mset)

        mhelp = tk.Menu(menubar, tearoff=0, bg=menu_bg, fg=menu_fg,
                        activebackground=active_bg, activeforeground=menu_fg,
                        font=menu_font)
        mhelp.add_command(label="关于", command=self.about)
        menubar.add_cascade(label="帮助", menu=mhelp)

        self.root.config(menu=menubar)
        # 快捷键只绑定一次，不在主题重建时重复绑定

    # ----------------------------------------------------------------- #
    # 主体
    # ----------------------------------------------------------------- #

    # 不使用主输入栏的标签页（内容占满全宽）
    _NO_INPUT_TABS = {"fingerprint", "experiment", "batch", "history"}

    def _build_body(self) -> None:
        body_padx = responsive_padding(12)
        body_pady = (responsive_padding(8), responsive_padding(4))
        body = ctk.CTkFrame(self.root, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=body_padx, pady=body_pady)
        self._body = body
        # 左栏固定像素宽：切换标签页时输入栏宽度恒定，不随右页内容跳动
        self._left_width = 340 if self._compact else 400
        body.grid_columnconfigure(0, weight=0, minsize=self._left_width)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # ── 左面板：输入卡片 ──
        left = ctk.CTkFrame(body, fg_color=s.CARD, corner_radius=10,
                            border_width=1, border_color=s.BORDER)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._left_panel = left
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left, text="📥 输入文本",
                     font=s.font("headline", bold=True), anchor="w"
                     ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))

        ctrl = ctk.CTkFrame(left, fg_color="transparent")
        ctrl.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 2))

        ctk.CTkLabel(ctrl, text="检测语言：", font=s.font("body")).pack(side="left")
        self.lang_var = tk.StringVar(value="自动")
        ctk.CTkOptionMenu(
            ctrl,
            variable=self.lang_var,
            values=["自动", "中文", "英文", "中英混合"],
            width=110, height=28,
            font=s.font("body"),
        ).pack(side="left", padx=(4, 8))
        ctk.CTkButton(ctrl, text="📋 加载示例", width=90, height=28,
                      fg_color=s.BUTTON_NEUTRAL, hover_color=s.BUTTON_NEUTRAL_HOVER,
                      text_color=s.TEXT, font=s.font("body"),
                      command=self.load_sample).pack(side="right", padx=(4, 0))
        ctk.CTkButton(ctrl, text="🗑 清空", width=70, height=28,
                      fg_color=s.BUTTON_NEUTRAL, hover_color=s.BUTTON_NEUTRAL_HOVER,
                      text_color=s.TEXT, font=s.font("body"),
                      command=self.clear_text).pack(side="right")

        self.text = ctk.CTkTextbox(
            left, wrap="word",
            font=s.font("headline", mono=True),
            border_width=1, border_color=s.BORDER,
        )
        self.text.grid(row=2, column=0, sticky="nsew", padx=12, pady=(6, 4))

        # 输入区底部提示
        ctk.CTkLabel(
            left,
            text="支持 txt / docx / pdf / html / md / rtf 等格式，可拖放或从菜单打开",
            font=s.font("caption"), text_color=s.MUTED, anchor="w",
        ).grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 10))

        # Placeholder 效果
        self._placeholder_shown = True
        self._placeholder_text = "在此粘贴或输入待分析文本……\n支持中文、英文及混合文本，也可从菜单「文件 → 打开」导入文档"
        self.text.insert("end", self._placeholder_text)
        self.text.configure(text_color=s.resolve(s.MUTED))
        self.text.bind("<FocusIn>", self._on_text_focus_in)
        self.text.bind("<FocusOut>", self._on_text_focus_out)

        # ── 右面板：标签页 ──
        # 注意：CTkSegmentedButton 只有一个 text_color（选中/未选中共用），
        # 因此未选中按钮底色用中性的墨绿灰，保证白字在两种模式下都可读。
        nb = ctk.CTkTabview(
            body,
            fg_color=s.CARD, corner_radius=10,
            border_width=1, border_color=s.BORDER,
            text_color=("#FFFFFF", "#E8ECEA"),
            segmented_button_fg_color=s.BG,
            segmented_button_selected_color=s.ACCENT,
            segmented_button_selected_hover_color=s.ACCENT_HOVER,
            segmented_button_unselected_color=("#6E7B76", "#2C3531"),
            segmented_button_unselected_hover_color=("#5C6963", "#3A4742"),
            anchor="w",
        )
        nb.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self.tabview = nb
        # CTkTabview.set() 不触发 command 回调：包装 set()，让程序化切页
        # （含点击、select_tab、脚本调用）都走同一套左面板显隐逻辑。
        _orig_tab_set = nb.set

        def _set_and_sync(title: str) -> None:
            _orig_tab_set(title)
            self._on_tab_changed()

        nb.set = _set_and_sync

        if self._compact:
            tab_titles = {
                "basic": "基础", "syntax": "句法", "compare": "对比",
                "viz": "可视化", "batch": "批量", "history": "历史",
                "fingerprint": "指纹", "experiment": "实验",
            }
        else:
            tab_titles = {
                "basic": "📊 基础分析", "syntax": "🔍 句法/语义",
                "compare": "⚖ 对比分析", "viz": "📈 可视化",
                "batch": "📁 批量处理", "history": "📜 历史记录",
                "fingerprint": "🔬 语言指纹", "experiment": "🧪 批量实验",
            }
        self._tab_titles = tab_titles
        self._title_to_key = {v: k for k, v in tab_titles.items()}

        tab_classes = [
            ("basic", BasicTab), ("syntax", SyntaxTab), ("compare", CompareTab),
            ("viz", VizTab), ("batch", BatchTab), ("history", HistoryTab),
            ("fingerprint", FingerprintTab), ("experiment", ExperimentTab),
        ]
        for key, cls in tab_classes:
            nb.add(tab_titles[key])
            tab = cls(nb.tab(tab_titles[key]), self)
            tab.pack(fill="both", expand=True)
            setattr(self, f"{key}_tab", tab)

    def select_tab(self, key: str) -> None:
        """切换到指定标签页（key 为 basic/syntax/compare/... 逻辑名）。"""
        title = self._tab_titles.get(key)
        if title:
            try:
                self.tabview.set(title)
            except Exception:
                pass
            # CTkTabview.set() 不触发 command 回调，手动同步一次
            self._on_tab_changed()

    def _on_tab_changed(self) -> None:
        """标签页切换：语言指纹/批量实验等不使用主输入栏的页隐藏左面板。"""
        if not hasattr(self, "_title_to_key"):
            return
        key = self._title_to_key.get(self.tabview.get(), "")
        if key == getattr(self, "_last_tab_key", None):
            return
        self._last_tab_key = key
        if key in self._NO_INPUT_TABS:
            self._left_panel.grid_remove()
            self._body.grid_columnconfigure(0, minsize=0)
        else:
            self._body.grid_columnconfigure(0, minsize=self._left_width)
            self._left_panel.grid()

    def _set_input_color(self, placeholder: bool) -> None:
        self.text.configure(text_color=s.resolve(s.MUTED if placeholder else s.TEXT))

    def _on_text_focus_in(self, event) -> None:
        if self._placeholder_shown:
            self.text.delete("1.0", "end")
            self._set_input_color(False)
            self._placeholder_shown = False

    def _on_text_focus_out(self, event) -> None:
        if not self.text.get("1.0", "end-1c").strip():
            self._placeholder_shown = True
            self.text.insert("end", self._placeholder_text)
            self._set_input_color(True)

    # ----------------------------------------------------------------- #
    # 状态栏
    # ----------------------------------------------------------------- #

    def _build_statusbar(self) -> None:
        bar = ctk.CTkFrame(self.root, fg_color=s.CARD, corner_radius=0, height=30)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self._status = ctk.CTkLabel(
            bar,
            text="就绪  —  输入文本后点击分析按钮开始",
            font=s.font("footnote"), text_color=s.MUTED,
            anchor="w", padx=16,
        )
        self._status.pack(fill="x")

    def set_status(self, msg: str) -> None:
        if hasattr(self, '_status'):
            self._status.configure(text=msg)

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

    def annotate_sentences(self, count: int) -> None:
        """分析完成后在句末插入不可见、不可选中的序号标记 ``[1] [2]``。

        实现要点：
        1. 标记用 ``\\x00[序号]\\x00`` 格式，用 NULL 字符包裹
           （正常文本不会包含 NULL，避免与正文冲突）。
        2. 标记带 ``elide=True`` 的 tag，Tk 会隐藏这些字符。
        3. ``get_text()`` 用正则过滤原始字符中的 NULL 标记。
        4. 点击标记区域 → 定位 → 展开对应句子。
        5. 用户修改文本（``<<Modified>>`` 事件）→ 自动清除所有标记。
        """
        if self._placeholder_shown or count <= 0:
            return

        # 先清除旧标记（真正删除字符，而非只删 tag）
        self.clear_sentence_marks()

        content = self.text.get("1.0", "end-1c")

        # 配置 elide tag（隐藏文本，Tk 8.5+ 支持）
        self.text.tag_config(
            "sent_marker",
            elide=True,
            foreground=s.resolve(s.ACCENT),
            background=s.resolve(s.ACCENT_SOFT),
            font=(s.FONT, s.responsive_font_size(s.FONT_SCALE["footnote"]) - 1, "bold"),
        )

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
        """删除所有句子序号标记（真正从文本中移除字符）。"""
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
            self._set_input_color(False)
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
        self.text.insert("end", self._placeholder_text)
        self._set_input_color(True)
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
        self._set_input_color(False)
        self._placeholder_shown = False
        self.set_status("已加载示例文本")

    def open_api_settings(self) -> None:
        dlg = ctk.CTkToplevel(self.root)
        dlg.title("API 配置")
        dlg.geometry("500x290")
        dlg.grab_set()
        dlg.transient(self.root)

        cfg = api_backend.load_config()

        ctk.CTkLabel(dlg, text="🔌 API 配置",
                     font=s.font("title2", bold=True)
                     ).pack(anchor="w", padx=16, pady=(14, 10))

        ctk.CTkLabel(dlg, text="Base URL（OpenAI 兼容）",
                     font=s.font("body")).pack(anchor="w", padx=16)
        base = ctk.CTkEntry(dlg, font=s.font("body", mono=True))
        base.insert(0, cfg.get("base_url", "https://api.openai.com/v1"))
        base.pack(padx=16, pady=(3, 0), fill="x")

        ctk.CTkLabel(dlg, text="API Key",
                     font=s.font("body")).pack(anchor="w", padx=16, pady=(10, 0))
        key = ctk.CTkEntry(dlg, show="*", font=s.font("body", mono=True))
        key.insert(0, cfg.get("api_key", ""))
        key.pack(padx=16, pady=(3, 0), fill="x")

        ctk.CTkLabel(dlg, text="模型名称",
                     font=s.font("body")).pack(anchor="w", padx=16, pady=(10, 0))
        model = ctk.CTkEntry(dlg, font=s.font("body", mono=True))
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

        btn_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=18)

        ctk.CTkButton(
            btn_frame, text="取消", width=90,
            fg_color=s.BUTTON_NEUTRAL, hover_color=s.BUTTON_NEUTRAL_HOVER,
            text_color=s.TEXT, font=s.font("body"),
            command=dlg.destroy,
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            btn_frame, text="💾 保存", width=90,
            font=s.font("body", bold=True),
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
            "📝 汉英 NLP 分析工具  V2.0.0\n"
            "Python + customtkinter · 本地与云端混合\n\n"
            "作者：Fragesius\n"
            "联系方式：fragesius@gmail.com\n\n"
            "本地引擎：jieba + spaCy + SnowNLP\n"
            "可选 AI：任意 OpenAI 兼容 API\n"
            "绘图：matplotlib + wordcloud\n\n"
            "支持深色/浅色主题切换",
        )


def show_first_run_setup(parent: ctk.CTk) -> bool:
    """首次运行向导：引导用户配置 API 密钥。"""
    from core._paths import mark_setup_done

    dlg = ctk.CTkToplevel(parent)
    dlg.title("欢迎使用")
    dlg.grab_set()
    dlg.transient(parent)

    # ── 响应式尺寸：确保所有内容可见 ──
    _, sh = s.get_screen_size()
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

    # 小屏幕启用滚动
    if sh <= 720:
        scrollable = ctk.CTkScrollableFrame(dlg, fg_color="transparent")
        scrollable.pack(fill="both", expand=True)
    else:
        scrollable = ctk.CTkFrame(dlg, fg_color="transparent")
        scrollable.pack(fill="both", expand=True)

    # ═══ 标题区 ═══
    ctk.CTkLabel(
        scrollable,
        text="欢迎使用汉英 NLP 分析工具",
        font=s.font("largeTitle", bold=True),
    ).pack(anchor="w", padx=tpad, pady=(tpad, 4))

    ctk.CTkLabel(
        scrollable,
        text="📝  本地优先 · 离线可用 · 可选 AI 增强",
        font=s.font("callout"), text_color=s.MUTED,
    ).pack(anchor="w", padx=tpad)

    # ═══ 功能卡片区 ═══
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

    card_container = ctk.CTkFrame(scrollable, fg_color="transparent")
    card_container.pack(fill="x", padx=tpad, pady=(16, 8))

    for icon, title, desc in features:
        card = ctk.CTkFrame(card_container, fg_color=s.BG, corner_radius=8)
        card.pack(fill="x", pady=card_vpad)

        ctk.CTkLabel(
            card, text=icon,
            font=s.font("title3"),
        ).pack(side="left", padx=(card_ipadx, 10), pady=card_ipady)

        text_col = ctk.CTkFrame(card, fg_color="transparent")
        text_col.pack(side="left", fill="x", expand=True, pady=card_ipady)

        ctk.CTkLabel(
            text_col, text=title,
            font=s.font("headline", bold=True),
            anchor="w",
        ).pack(fill="x")

        ctk.CTkLabel(
            text_col, text=desc,
            font=s.font("footnote"), text_color=s.MUTED,
            anchor="w",
        ).pack(fill="x", pady=(1, 0))

    # ═══ 提示 ═══
    ctk.CTkLabel(
        scrollable,
        text="💡 可稍后在菜单栏「设置 → API 配置」中随时修改。",
        font=s.font("caption"), text_color=s.MUTED,
    ).pack(anchor="w", padx=tpad, pady=(0, 8))

    # ═══ 分隔线 ═══
    ctk.CTkFrame(scrollable, fg_color=s.BORDER, height=1,
                 corner_radius=0).pack(fill="x", padx=tpad)

    # ═══ 按钮区 ═══
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

    btn_frame = ctk.CTkFrame(scrollable, fg_color="transparent")
    btn_frame.pack(fill="x", padx=tpad, pady=(16, 0))

    # 主要操作（右）— Accent
    ctk.CTkButton(
        btn_frame, text="🔌 配置 API 密钥",
        font=s.font("body", bold=True),
        height=40, width=170,
        command=_do_configure,
    ).pack(side="right")

    # 次要操作（左）
    ctk.CTkButton(
        btn_frame, text="跳过，使用本地分析",
        font=s.font("body"),
        height=40,
        fg_color="transparent", hover_color=s.BUTTON_NEUTRAL_HOVER,
        text_color=s.MUTED,
        command=_do_skip,
    ).pack(side="left")

    # ── "不再提示" ──
    ctk.CTkCheckBox(
        scrollable,
        text="下次不再显示此向导",
        variable=skip,
        font=s.font("footnote"),
        text_color=s.MUTED,
    ).pack(anchor="w", padx=tpad, pady=(12, tpad))

    # 等待对话框关闭
    parent.wait_window(dlg)
    return result["configured"]


def main() -> None:
    enable_dpi_awareness()
    s.init_appearance()          # 跟随系统深/浅色 + 墨绿主题
    root = ctk.CTk()

    app = App(root)
    # 注册以便 setup 对话框能调用 app.open_api_settings()
    root._app_instance = app

    # ── 首次运行向导 ──
    from core._paths import is_first_run
    from core import api_backend

    if is_first_run() and not api_backend.is_configured():
        # 延迟弹出，等主窗口先渲染
        root.after(400, lambda: show_first_run_setup(root))

    root.mainloop()


if __name__ == "__main__":
    main()
