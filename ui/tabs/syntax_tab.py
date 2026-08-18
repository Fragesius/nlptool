"""句法 / 语义分析标签页（customtkinter 版）。"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import Optional

import customtkinter as ctk

from core import analyzer, api_backend, history
from ui.async_runner import TaskRunner
from ui import style as s
from ui.tabs.widgets import (
    Card, accent_btn, flat_btn,
    make_labeled_text, add_copy_button, textbox_getter,
    _ner_status_msg, _dep_status_msg,
)


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
        add_copy_button(self.ner_tab, textbox_getter(self.ner_text))
        self.kw_text = make_labeled_text(self.kw_tab, "关键词  —  词语 / 权重")
        add_copy_button(self.kw_tab, textbox_getter(self.kw_text))

        # ── 依存句法：文字列表（可视化请在「可视化」标签查看树图）──
        self.dep_text = make_labeled_text(
            self.dep_tab,
            "依存关系  —  词元(词性)  ──依存──▶  head(head词性)"
        )
        add_copy_button(self.dep_tab, textbox_getter(self.dep_text))
        self._dep_sentences: list[list[dict]] = []

        self.sent_text = make_labeled_text(self.sent_tab, "情感得分  —  -1 负向  ~  1 正向")
        add_copy_button(self.sent_tab, textbox_getter(self.sent_text))
        self.api_text = make_labeled_text(self.api_tab, "AI 返回结果")
        add_copy_button(self.api_tab, textbox_getter(self.api_text))

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
