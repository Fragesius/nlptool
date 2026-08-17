"""后台任务运行器。

为耗时操作（spaCy 分析、语言指纹、API 调用、批量处理等）提供：
- 独立工作线程，不阻塞 Tkinter 主事件循环
- 模态进度对话框 + 取消按钮
- 成功/失败回调通过线程安全队列自动切回主线程
- 统一的异常包装与友好错误提示

用法示例::

    runner = TaskRunner(parent)
    runner.run(
        analyzer.analyze_syntax,
        args=(text, lang),
        on_success=lambda res: show_result(res),
        on_error=lambda e: show_error(e),
        title="句法分析",
        message="正在解析依存关系...",
    )
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Callable, Optional, Tuple, Any

import customtkinter as ctk

from ui import style as s


class TaskCancelled(Exception):
    """用户点击取消按钮时抛出。"""

    pass


class TaskRunner:
    """在后台线程运行任务，并通过队列将结果切回主线程处理。"""

    def __init__(self, parent: tk.Widget):
        self.parent = parent
        self._dialog: Optional[ctk.CTkToplevel] = None
        self._cancelled = threading.Event()
        self._running = False
        self._queue: queue.Queue = queue.Queue()
        self._polling = False
        self._task_gen = 0  # 任务世代计数器，防止取消/新任务后收到旧结果

    # --------------------------------------------------------------------- #
    # 公共 API
    # --------------------------------------------------------------------- #

    def run(
        self,
        task: Callable,
        args: Tuple = (),
        kwargs: Optional[dict] = None,
        on_success: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        title: str = "处理中",
        message: str = "请稍候...",
        cancellable: bool = True,
        show_dialog: bool = True,
    ) -> None:
        """启动后台任务并显示进度对话框。

        Args:
            task: 在后台线程执行的函数。
            args, kwargs: 传给 task 的位置参数和关键字参数。
            on_success: 成功时调用，参数为 task 返回值。
            on_error: 失败时调用，参数为 Exception。若未提供则弹错误对话框。
            title: 进度对话框标题。
            message: 进度对话框提示文本。
            cancellable: 是否显示取消按钮。
            show_dialog: False 时不弹模态进度对话框（调用方自行展示
                进度，例如内嵌确定性进度条）。
        """
        if self._running:
            # 当前已在运行：忽略重复调用（调用方应自行防重入）
            return

        self._task_gen += 1
        current_gen = self._task_gen
        self._running = True
        self._cancelled.clear()
        kwargs = kwargs or {}

        if show_dialog:
            self._show_dialog(title, message, cancellable)
        self._start_polling()

        def _target():
            result = None
            error: Optional[Exception] = None
            try:
                result = task(*args, **kwargs)
            except TaskCancelled:
                error = TaskCancelled("已取消")
            except Exception as e:
                error = e
            finally:
                self._running = False

            # 将结果放入队列，由主线程轮询处理
            self._queue.put((current_gen, result, error, on_success, on_error))

        thread = threading.Thread(target=_target, daemon=True)
        thread.start()

    def is_running(self) -> bool:
        return self._running

    # --------------------------------------------------------------------- #
    # 内部
    # --------------------------------------------------------------------- #

    def _show_dialog(self, title: str, message: str, cancellable: bool) -> None:
        self._dialog = ctk.CTkToplevel(self.parent)
        self._dialog.title(title)
        self._dialog.transient(self.parent.winfo_toplevel())
        self._dialog.resizable(False, False)
        self._dialog.geometry("380x150")

        # 居中于父窗口
        self._dialog.update_idletasks()
        parent = self.parent.winfo_toplevel()
        px, py = parent.winfo_x(), parent.winfo_y()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        dx, dy = 380, 150
        self._dialog.geometry(f"+{px + (pw - dx) // 2}+{py + (ph - dy) // 2}")
        self._dialog.grab_set()

        frame = ctk.CTkFrame(self._dialog, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            frame,
            text=message,
            font=s.font("body"),
            wraplength=320,
            justify="left",
        ).pack(anchor="w", pady=(0, 12))

        self._progress = ctk.CTkProgressBar(frame, mode="indeterminate", width=320)
        self._progress.pack(fill="x", pady=(0, 12))
        self._progress.start()

        if cancellable:
            btn = ctk.CTkButton(
                frame,
                text="取消",
                font=s.font("body"),
                width=90,
                fg_color=s.BUTTON_NEUTRAL,
                hover_color=s.BUTTON_NEUTRAL_HOVER,
                text_color=s.TEXT,
                command=self._cancel,
            )
            btn.pack(anchor="e")

    def _cancel(self) -> None:
        self._cancelled.set()
        if self._dialog is not None:
            self._dialog.grab_release()
            self._dialog.destroy()
            self._dialog = None

    def _start_polling(self) -> None:
        if not self._polling:
            self._polling = True
            self._poll()

    def _poll(self) -> None:
        """主线程轮询队列，处理后台任务结果。"""
        try:
            while True:
                item = self._queue.get_nowait()
                self._process_queue_item(item)
        except queue.Empty:
            pass

        # 若任务仍在运行或对话框仍在，继续轮询
        if self._running or self._dialog is not None:
            self.parent.after(100, self._poll)
        else:
            self._polling = False

    def _process_queue_item(self, item: tuple) -> None:
        gen, result, error, on_success, on_error = item

        # 忽略旧任务的结果（用户已取消或已启动新任务）
        if gen != self._task_gen:
            return

        if self._dialog is not None:
            self._dialog.grab_release()
            self._dialog.destroy()
            self._dialog = None

        if isinstance(error, TaskCancelled):
            return  # 静默忽略用户取消

        if error is not None:
            if on_error is not None:
                on_error(error)
            else:
                messagebox.showerror("任务失败", str(error))
        else:
            if on_success is not None:
                on_success(result)

    # --------------------------------------------------------------------- #
    # 给任务函数使用的取消检查辅助
    # --------------------------------------------------------------------- #

    def check_cancelled(self) -> None:
        """长任务可在循环中调用此方法以响应取消。"""
        if self._cancelled.is_set():
            raise TaskCancelled("已取消")
