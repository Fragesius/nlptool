"""对比分析与可读性模块测试。"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.comparison import english_readability, align_zh_en


def test_english_readability():
    text = "The cat sat on the mat. It was happy."
    res = english_readability(text)
    assert isinstance(res.flesch_ease, float)
    assert isinstance(res.flesch_kincaid, float)
    assert res.avg_sentence_length > 0


def test_align_zh_en():
    zh = "这是第一句。这是第二句。"
    en = "This is the first sentence. This is the second sentence."
    res = align_zh_en(zh, en)
    assert len(res.pairs) == 2
