"""spaCy 缺失时降级路径的回归测试。

回归背景：``core.analyzer._get_spacy`` 曾在模型加载失败时引用未赋值的
``model`` 变量，抛 ``UnboundLocalError``，导致英文分词 / 基础统计 / KWIC
在未安装 spaCy 或 en_core_web_sm 的环境中直接崩溃。

覆盖两种缺失场景（与真实环境是否装了 spaCy 无关，密封可重复）：
- ``no_pkg``：spaCy 包未安装 —— ``import spacy`` 抛 ``ImportError``
  （``sys.modules["spacy"] = None`` 会使 import 直接失败）；
- ``no_model``：包已装但模型缺失 —— 假 ``spacy`` 模块的 ``load`` 抛 ``OSError``。

兼容无 pytest 的 ``python run_tests.py``：测试函数均为零参数，
用 contextmanager 手动 mock 而非 pytest 的 monkeypatch fixture。
"""

import sys
import types
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core.analyzer as analyzer
from core.concordance import kwic


def _make_broken_spacy() -> types.ModuleType:
    """构造一个 ``load`` 总是抛 ``OSError`` 的假 spacy 模块（模型缺失）。"""
    fake = types.ModuleType("spacy")

    def _raise(*args, **kwargs):
        raise OSError("mock: model 'en_core_web_sm' not found")

    fake.load = _raise
    return fake


@contextmanager
def _spacy_env(kind: str):
    """模拟 spaCy 不可用环境，退出后恢复 ``_spacy_nlp`` 缓存与 sys.modules。

    :param kind: ``"no_pkg"``（包未安装，import 抛 ImportError）或
                 ``"no_model"``（包已装但模型缺失，load 抛 OSError）
    """
    old_cache = dict(analyzer._spacy_nlp)
    had_spacy = "spacy" in sys.modules
    old_spacy = sys.modules.get("spacy")
    analyzer._spacy_nlp.clear()
    if kind == "no_pkg":
        # None 会让 `import spacy` 抛 ImportError，模拟包未安装
        sys.modules["spacy"] = None
    else:
        sys.modules["spacy"] = _make_broken_spacy()
    try:
        yield
    finally:
        analyzer._spacy_nlp.clear()
        analyzer._spacy_nlp.update(old_cache)
        if had_spacy:
            sys.modules["spacy"] = old_spacy
        else:
            sys.modules.pop("spacy", None)


def test_get_spacy_returns_false_when_unavailable():
    """两种缺失场景下：只警告、不崩溃，按约定返回 False。"""
    for kind in ("no_pkg", "no_model"):
        with _spacy_env(kind):
            assert analyzer._get_spacy("en") is False
            # 失败结果被缓存，重复调用同样安全
            assert analyzer._get_spacy("en") is False


def test_tokenize_en_fallback_regex():
    """英文分词降级到正则路径，返回结构正确的 Token 列表。"""
    for kind in ("no_pkg", "no_model"):
        with _spacy_env(kind):
            tokens = analyzer.tokenize_en("Hello world. Hello again.")
        assert [t.text for t in tokens] == ["Hello", "world", "Hello", "again"]
        assert all(t.lang == "en" for t in tokens)
        assert all(t.pos == "WORD" for t in tokens)
        assert [t.lemma for t in tokens] == ["hello", "world", "hello", "again"]


def test_analyze_basic_counts_fallback():
    """基础统计在降级模式下正常（回归 test_analyze_basic_counts 的崩溃）。"""
    for kind in ("no_pkg", "no_model"):
        with _spacy_env(kind):
            res = analyzer.analyze_basic("Hello world. Hello again.", "en")
        assert res.sentence_count == 2
        assert res.word_count >= 4
        assert res.freq["hello"] == 2


def test_kwic_fallback():
    """KWIC 检索在降级模式下正常（回归 test_concordance 的崩溃）。"""
    text = "The cat sat on the mat. The dog sat on the log."
    for kind in ("no_pkg", "no_model"):
        with _spacy_env(kind):
            lines = kwic(text, "sat", lang="en", window=2)
        assert len(lines) == 2
        assert all(line.keyword.lower() == "sat" for line in lines)
        assert all(isinstance(line.left, str) and isinstance(line.right, str) for line in lines)
