"""核心分析模块测试。"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.analyzer import (
    detect_language,
    split_sentences,
    tokenize,
    analyze_basic,
)


def test_detect_language_zh():
    assert detect_language("今天天气很好。") == "zh"


def test_detect_language_en():
    assert detect_language("The quick brown fox jumps.") == "en"


def test_detect_language_mixed():
    text = "自然语言处理很有趣。I love NLP!"
    assert detect_language(text) == "mixed"


def test_split_sentences_zh():
    text = "今天很好。明天呢？出发吧！"
    sents = split_sentences(text)
    assert len(sents) == 3


def test_split_sentences_en_abbreviations():
    text = "Dr. Smith went to Washington. He saw Mr. Jones."
    sents = split_sentences(text)
    assert len(sents) == 2


def test_analyze_basic_counts():
    text = "Hello world. Hello again."
    res = analyze_basic(text, "en")
    assert res.sentence_count == 2
    assert res.word_count >= 4
    assert res.freq["hello"] == 2
