"""共现 / KWIC 模块测试。"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.concordance import kwic


def test_kwic_basic():
    text = "The cat sat on the mat. The dog sat on the log."
    lines = kwic(text, "sat", lang="en", window=2)
    assert len(lines) == 2
    assert all(line.keyword.lower() == "sat" for line in lines)


def test_kwic_case_insensitive():
    text = "The Cat sat."
    lines = kwic(text, "cat", lang="en", case_sensitive=False)
    assert len(lines) == 1


def test_kwic_no_match():
    text = "The cat sat."
    lines = kwic(text, "dog", lang="en")
    assert len(lines) == 0
