"""TaskRunner 取消语义测试（纯逻辑，不启动真实 GUI 主循环）。

用假 parent（after 为 no-op）绕开 Tkinter 事件循环，
手动驱动 _cancel / _process_queue_item 验证：
- check_cancelled 在取消事件 set 后抛 TaskCancelled；
- 用户取消后迟到的结果被 gen 检查丢弃，on_success 不上屏；
- on_cancel 恰好调用一次；
- 上个任务已取消（线程退出中）时允许立即启动新任务；
- 任务正常进行中重复 run 仍被忽略。
"""

import threading

from ui.async_runner import TaskCancelled, TaskRunner


class _FakeParent:
    """最小 parent 替身：after 不真正调度（测试中手动驱动）。"""

    def after(self, ms, cb=None, *args):
        return None


def _drain_and_process(runner, timeout=5.0):
    """至少等待一个结果入队，然后取走全部已入队结果并逐个处理。"""
    import queue as _q

    items = [runner._queue.get(timeout=timeout)]
    while True:
        try:
            items.append(runner._queue.get_nowait())
        except _q.Empty:
            break
    for item in items:
        runner._process_queue_item(item)
    return items


def test_check_cancelled_raises_when_event_set():
    runner = TaskRunner(_FakeParent())
    # 未 set 时不抛
    runner.check_cancelled()
    runner._cancelled.set()
    try:
        runner.check_cancelled()
    except TaskCancelled:
        return
    raise AssertionError("check_cancelled 未在取消事件 set 后抛 TaskCancelled")


def test_cancel_discards_late_result_and_fires_on_cancel_once():
    runner = TaskRunner(_FakeParent())
    started = threading.Event()
    release = threading.Event()
    successes = []
    cancels = []

    def task():
        started.set()
        release.wait(5)
        return "done"

    runner.run(
        task,
        show_dialog=False,
        on_success=successes.append,
        on_cancel=lambda: cancels.append(1),
    )
    assert started.wait(5), "任务线程未启动"

    runner._cancel()
    # on_cancel 在点击时立即调用一次
    assert cancels == [1]
    assert runner._cancelled.is_set()

    # 放跑任务线程，其迟到结果应被 gen 检查丢弃
    release.set()
    _drain_and_process(runner)
    assert successes == [], "取消后迟到结果不应触发 on_success"
    assert cancels == [1], "on_cancel 不应被二次调用"


def test_task_cancelled_result_with_matching_gen_fires_on_cancel():
    """任务经 check_cancelled 自行抛 TaskCancelled（gen 未 bump）时，
    _process_queue_item 应调用 on_cancel 复位 UI 且不触发其他回调。"""
    runner = TaskRunner(_FakeParent())
    successes = []
    errors = []
    cancels = []

    def task():
        raise TaskCancelled("已取消")

    runner.run(
        task,
        show_dialog=False,
        on_success=successes.append,
        on_error=errors.append,
        on_cancel=lambda: cancels.append(1),
    )
    _drain_and_process(runner)
    assert successes == []
    assert errors == []
    assert cancels == [1]


def test_restart_allowed_after_cancel():
    """上个任务已取消、线程尚未退出时，允许立即启动新任务。"""
    runner = TaskRunner(_FakeParent())
    started1 = threading.Event()
    release1 = threading.Event()
    successes = []

    def task1():
        started1.set()
        release1.wait(5)
        return "old"

    def task2():
        return "new"

    runner.run(task1, show_dialog=False, on_success=successes.append)
    assert started1.wait(5)
    runner._cancel()

    # 旧线程仍阻塞在 release1 上，但应允许立即启动新任务
    gen_before = runner._task_gen
    runner.run(task2, show_dialog=False, on_success=successes.append)
    assert runner._task_gen > gen_before, "取消后应立即允许新任务"

    # 新任务结果正常上屏；随后放跑旧任务，其结果被丢弃
    _drain_and_process(runner)
    release1.set()
    _drain_and_process(runner)
    assert successes == ["new"], f"期望仅新任务结果上屏，实际 {successes}"


def test_duplicate_run_ignored_while_running():
    runner = TaskRunner(_FakeParent())
    started = threading.Event()
    release = threading.Event()
    task2_started = threading.Event()

    def task1():
        started.set()
        release.wait(5)
        return 1

    def task2():
        task2_started.set()
        return 2

    runner.run(task1, show_dialog=False)
    assert started.wait(5)
    gen = runner._task_gen
    runner.run(task2, show_dialog=False)
    assert runner._task_gen == gen, "任务进行中重复 run 应被忽略"
    assert not task2_started.is_set(), "被忽略的任务不应启动"
    release.set()
    _drain_and_process(runner)


def test_report_progress_no_dialog_is_noop():
    runner = TaskRunner(_FakeParent())
    # 无对话框：安全 no-op，不抛异常
    runner.report_progress(3, 10)
    runner._apply_progress(3, 10)
