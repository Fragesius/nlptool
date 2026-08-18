"""各功能标签页（customtkinter 版）。

布局统一为「输入设置 / 运行控制 / 结果展示」三段式卡片分区，
强调色与配色常量集中在 ui.style。
"""

from ui.tabs.widgets import (
    clear_widget, Card, accent_btn, flat_btn, hint_label,
    make_labeled_text, add_copy_button, textbox_getter, embed_figure,
    _ner_status_msg, _dep_status_msg,
)
from ui.tabs.basic_tab import BasicTab
from ui.tabs.syntax_tab import SyntaxTab
from ui.tabs.compare_tab import CompareTab
from ui.tabs.history_tab import HistoryTab
from ui.tabs.viz_tab import VizTab
from ui.tabs.fingerprint_tab import _InputRow, _ControlRow, FingerprintTab
from ui.tabs.batch_tab import BatchTab
from ui.tabs.experiment_tab import ExperimentTab
