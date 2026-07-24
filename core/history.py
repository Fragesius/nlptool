"""分析历史记录管理。

数据存储在 ``_data/history.json``（软件目录下），最多保留 200 条。
便携版：复制文件夹即可迁移全部数据。
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from core._paths import HISTORY_PATH, ensure_data_dirs

STORE_DIR = os.path.dirname(HISTORY_PATH)
STORE_PATH = HISTORY_PATH
MAX_ENTRIES = 200


@dataclass
class HistoryEntry:
    id: str
    timestamp: str  # ISO 8601
    input_text: str
    lang: str
    # 基础分析摘要
    basic_summary: str = ""
    tokens_preview: str = ""  # 前若干词的文本预览
    freq_preview: str = ""  # 词频 Top 10 预览
    # 句法/语义 摘要
    ner_preview: str = ""
    keywords_preview: str = ""
    sentiment_label: str = ""
    sentiment_score: float = 0.0

    def as_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "HistoryEntry":
        return cls(**d)


# --------------------------------------------------------------------------- #
# 读写
# --------------------------------------------------------------------------- #


def _ensure_store() -> None:
    ensure_data_dirs()


def load_all() -> List[HistoryEntry]:
    _ensure_store()
    if not os.path.exists(STORE_PATH):
        return []
    try:
        with open(STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [HistoryEntry.from_dict(d) for d in data]
    except Exception:
        return []


def save_all(entries: List[HistoryEntry]) -> None:
    _ensure_store()
    entries = entries[-MAX_ENTRIES:]  # 最多保留
    with open(STORE_PATH, "w", encoding="utf-8") as f:
        json.dump([e.as_dict() for e in entries], f, ensure_ascii=False, indent=2)


def add_entry(entry: HistoryEntry) -> None:
    entries = load_all()
    entries.append(entry)
    save_all(entries)


def delete_entry(eid: str) -> None:
    entries = load_all()
    entries = [e for e in entries if e.id != eid]
    save_all(entries)


def clear_all() -> None:
    if os.path.exists(STORE_PATH):
        os.remove(STORE_PATH)


def build_entry(
    text: str,
    lang: str,
    basic_summary: str = "",
    tokens_preview: str = "",
    freq_preview: str = "",
    ner_preview: str = "",
    keywords_preview: str = "",
    sentiment_label: str = "",
    sentiment_score: float = 0.0,
) -> HistoryEntry:
    return HistoryEntry(
        id=uuid.uuid4().hex[:12],
        timestamp=datetime.now().isoformat(timespec="seconds"),
        input_text=text,
        lang=lang,
        basic_summary=basic_summary,
        tokens_preview=tokens_preview,
        freq_preview=freq_preview,
        ner_preview=ner_preview,
        keywords_preview=keywords_preview,
        sentiment_label=sentiment_label,
        sentiment_score=sentiment_score,
    )
