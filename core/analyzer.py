"""NLP 核心分析引擎。

设计要点：
- 中英文统一接口，语言可自动检测或手动指定。
- 重型依赖（jieba / spaCy / snownlp / nltk）按需懒加载，缺失时优雅降级
  到内置实现，保证应用在最小依赖下也能运行。
- 高级分析可选调用在线 API（见 :mod:`core.api_backend`）。
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Optional

# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #


@dataclass
class Token:
    """单个词元。"""

    text: str
    pos: str = ""  # 词性标签
    lemma: str = ""  # 词形还原（英文）
    is_stop: bool = False
    lang: str = ""  # 'zh' / 'en'

    def as_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class Sentence:
    """切分后的句子。"""

    text: str
    lang: str = ""
    tokens: List[Token] = field(default_factory=list)


@dataclass
class BasicResult:
    """基础分析结果。"""

    lang: str
    text: str
    tokens: List[Token]
    sentences: List[Sentence]
    char_count: int
    char_count_no_space: int
    word_count: int
    sentence_count: int
    freq: Counter  # 词频（去除空白与标点）
    pos_dist: Counter  # 词性分布

    def summary(self) -> str:
        lines = [
            f"语言: {self.lang_name()}",
            f"字符数: {self.char_count}（不含空格 {self.char_count_no_space}）",
            f"词元数: {self.word_count}",
            f"句子数: {self.sentence_count}",
            f"平均句长: {self.word_count / self.sentence_count:.1f} 词/句"
            if self.sentence_count
            else "平均句长: 0",
        ]
        return "\n".join(lines)

    def lang_name(self) -> str:
        return {"zh": "中文", "en": "英文", "mixed": "中英混合"}.get(self.lang, self.lang)


@dataclass
class SyntaxResult:
    """句法 / 语义分析结果。"""

    ner: List[dict]  # 命名实体 [{text, label, start, end}]
    keywords: List[tuple]  # [(word, weight)]
    dependencies: List[dict]  # 依存关系 [{text, dep, head_text, head_pos}]
    sentiment: dict  # {label, score, raw}
    pos_tags: List[dict]  # 带词性的词元序列


# --------------------------------------------------------------------------- #
# 语言检测
# --------------------------------------------------------------------------- #

_CJK_RE = re.compile(r"[一-鿿]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def detect_language(text: str) -> str:
    """粗略检测语言：统计 CJK 与拉丁字母占比。

    两者都有且占比不过分悬殊时判定为「中英混合」，交由分词器按段处理，
    避免某一种语言的字符被另一语言的分词器丢弃。
    """
    if not text:
        return "zh"
    cjk = len(_CJK_RE.findall(text))
    latin = len(_LATIN_RE.findall(text))
    if cjk == 0 and latin == 0:
        return "zh"
    if cjk == 0:
        return "en"
    if latin == 0:
        return "zh"
    # 两者都存在：若少数方占比 >= 20% 则视为混合
    ratio = min(cjk, latin) / max(cjk, latin)
    if ratio >= 0.2:
        return "mixed"
    return "zh" if cjk > latin else "en"


# --------------------------------------------------------------------------- #
# 句子切分
# --------------------------------------------------------------------------- #

# 中文句末标点 + 英文句末标点
_SENT_SPLIT_RE = re.compile(r"([^。！？!?\.\n]+[。！？!?]|\S[^。！？!?\.\n]*\.(?=\s|$)|[^\n。！？!?]+(?=\n|$))")


def split_sentences(text: str) -> List[str]:
    """切分句子，兼顾中英文标点。"""
    text = text.strip()
    if not text:
        return []
    sents = _SENT_SPLIT_RE.findall(text)
    # 过滤纯空白
    return [s.strip() for s in sents if s.strip()]


# --------------------------------------------------------------------------- #
# 懒加载后端
# --------------------------------------------------------------------------- #

_jieba = None
_jieba_pos = None
_spacy_nlp = {}  # lang -> nlp or False


def _get_jieba():
    global _jieba, _jieba_pos
    if _jieba is None:
        try:
            import jieba  # type: ignore
            import jieba.posseg as pseg  # type: ignore

            # 便携模式：jieba 缓存写入 _data/cache/ 而非系统 TEMP
            from core._paths import JIEBA_CACHE, ensure_data_dirs
            ensure_data_dirs()
            cache_dir = os.path.dirname(JIEBA_CACHE)
            jieba.dt.tmp_dir = cache_dir
            pseg.dt.tmp_dir = cache_dir

            _jieba = jieba
            _jieba_pos = pseg
        except ImportError:
            _jieba = False
    return _jieba, _jieba_pos


def _get_spacy(lang: str = "en"):
    """返回 spaCy 管线，缺失则返回 False。"""
    if lang not in _spacy_nlp:
        try:
            import spacy  # type: ignore

            model = {"en": "en_core_web_sm", "zh": "zh_core_web_sm"}[lang]

            # PyInstaller 打包后在 _internal 目录中找模型
            if getattr(sys, "frozen", False):
                model_dir = os.path.join(sys._MEIPASS, model)  # type: ignore[attr-defined]
                # spaCy 模型目录结构：外层 meta.json，内层 <model>-<ver>/ 含 config.cfg
                for entry in os.listdir(model_dir):
                    inner = os.path.join(model_dir, entry)
                    if os.path.isdir(inner) and os.path.exists(os.path.join(inner, "config.cfg")):
                        model_dir = inner
                        break
                _spacy_nlp[lang] = spacy.load(model_dir)
            else:
                _spacy_nlp[lang] = spacy.load(model)
        except Exception:
            _spacy_nlp[lang] = False
    return _spacy_nlp[lang]


# --------------------------------------------------------------------------- #
# 内置停用词与极简情感词典（保证离线可用）
# --------------------------------------------------------------------------- #

_EN_STOP = set(
    "the a an of to in on at for and or but is are was were be been being this that "
    "these those it its as with by from he she they we i you my your his her their our "
    "not no do does did have has had will would can could should may might must".split()
)

_ZH_STOP = set(
    "的 了 和 是 在 我 有 与 及 或 但 而 也 这 那 你 他 她 它 我们 你们 他们 "
    "个 之 着 过 都 就 还 又 把 被 让 使 对 从 给 向 为 以 于 不 没 没有".split()
)

_EN_POS = set("good great nice excellent wonderful happy love like best amazing perfect positive".split())
_EN_NEG = set("bad terrible awful horrible sad hate dislike worst poor negative ugly wrong".split())
_ZH_POS = set("好 喜欢 优秀 开心 快乐 满意 爱 赞 美好 棒 不错 优秀 成功".split())
_ZH_NEG = set("坏 差 讨厌 糟糕 难过 失败 痛苦 愤怒 失望 错 烂 不行".split())


def _is_punct(tok: str) -> bool:
    return not re.search(r"[\w一-鿿]", tok)


# --------------------------------------------------------------------------- #
# 分词
# --------------------------------------------------------------------------- #


def tokenize_zh(text: str) -> List[Token]:
    """中文分词（jieba 优先，回退到字符切分）。"""
    jieba, pseg = _get_jieba()
    tokens: List[Token] = []
    if jieba and pseg:
        for w, flag in pseg.cut(text):
            if not w.strip():
                continue
            tokens.append(
                Token(text=w, pos=flag, lemma=w, is_stop=w in _ZH_STOP, lang="zh")
            )
    else:
        # 回退：按字符切分非标点 CJK
        for ch in text:
            if _CJK_RE.match(ch):
                tokens.append(Token(text=ch, pos="x", lang="zh", is_stop=ch in _ZH_STOP))
            elif ch.strip() and not _is_punct(ch):
                tokens.append(Token(text=ch, pos="x", lang="zh"))
    return tokens


def tokenize_en(text: str) -> List[Token]:
    """英文分词（spaCy 优先，回退到正则）。"""
    nlp = _get_spacy("en")
    tokens: List[Token] = []
    if nlp:
        doc = nlp(text)
        for t in doc:
            if t.is_space:
                continue
            tokens.append(
                Token(
                    text=t.text,
                    pos=t.pos_,
                    lemma=t.lemma_.lower(),
                    is_stop=t.is_stop or t.text.lower() in _EN_STOP,
                    lang="en",
                )
            )
    else:
        # 回退：正则分词
        for raw in re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)*", text):
            low = raw.lower()
            tokens.append(
                Token(text=raw, pos="WORD", lemma=low, is_stop=low in _EN_STOP, lang="en")
            )
    return tokens


def tokenize(text: str, lang: Optional[str] = None) -> List[Token]:
    """统一分词入口，支持混合文本按段分词。"""
    lang = lang or detect_language(text)
    if lang == "zh":
        return tokenize_zh(text)
    if lang == "en":
        return tokenize_en(text)
    # mixed：按 CJK / 拉丁片段分别处理
    tokens: List[Token] = []
    # 用正则切出中文段与英文段
    for seg in re.findall(r"[一-鿿]+|[A-Za-z][A-Za-z\s.,;:!?'\"-]*", text):
        if _CJK_RE.search(seg):
            tokens.extend(tokenize_zh(seg))
        elif seg.strip():
            tokens.extend(tokenize_en(seg))
    return tokens


# --------------------------------------------------------------------------- #
# 基础分析
# --------------------------------------------------------------------------- #


def analyze_basic(text: str, lang: Optional[str] = None) -> BasicResult:
    """执行基础分析：分词、句子切分、统计、词频、词性分布。"""
    lang = lang or detect_language(text)
    tokens = tokenize(text, lang)
    sents_text = split_sentences(text)

    sentences: List[Sentence] = []
    for s in sents_text:
        s_lang = detect_language(s)
        sentences.append(Sentence(text=s, lang=s_lang, tokens=tokenize(s, s_lang)))

    # 词频：去掉标点与停用词
    meaningful = [
        t.lemma or t.text
        for t in tokens
        if not _is_punct(t.text) and not t.is_stop and t.text.strip()
    ]
    freq = Counter(meaningful)
    pos_dist = Counter(t.pos for t in tokens if t.text.strip())

    return BasicResult(
        lang=lang,
        text=text,
        tokens=tokens,
        sentences=sentences,
        char_count=len(text),
        char_count_no_space=len(text.replace(" ", "").replace("\n", "")),
        word_count=len(tokens),
        sentence_count=len(sentences),
        freq=freq,
        pos_dist=pos_dist,
    )


# --------------------------------------------------------------------------- #
# 句法 / 语义
# --------------------------------------------------------------------------- #


def extract_keywords(text: str, lang: Optional[str] = None, topk: int = 15) -> List[tuple]:
    """关键词提取。中文用 jieba TF-IDF，英文用 spaCy 名词短语 + 词频。"""
    lang = lang or detect_language(text)
    jieba, _ = _get_jieba()
    if lang == "zh" and jieba:
        try:
            from jieba import analyse  # type: ignore

            return [(w, round(s, 4)) for w, s in analyse.extract_tags(text, topK=topk, withWeight=True)]
        except Exception:
            pass
    # 通用回退：基于词频
    res = analyze_basic(text, lang)
    return res.freq.most_common(topk)


def named_entities(text: str, lang: Optional[str] = None) -> List[dict]:
    """命名实体识别（主要依赖 spaCy）。"""
    lang = lang or detect_language(text)
    nlp = _get_spacy(lang if lang in ("en", "zh") else "en")
    if not nlp:
        return []
    doc = nlp(text)
    return [
        {"text": ent.text, "label": ent.label_, "start": ent.start_char, "end": ent.end_char}
        for ent in doc.ents
    ]


def dependencies(text: str, lang: Optional[str] = None) -> List[dict]:
    """依存句法分析（依赖 spaCy）。"""
    lang = lang or detect_language(text)
    nlp = _get_spacy(lang if lang in ("en", "zh") else "en")
    if not nlp:
        return []
    doc = nlp(text)
    deps = []
    for t in doc:
        if t.is_space:
            continue
        deps.append(
            {
                "text": t.text,
                "pos": t.pos_,
                "dep": t.dep_,
                "head_text": t.head.text,
                "head_pos": t.head.pos_,
                "head_i": t.head.i,  # head 的 token 序号，消除重复词歧义
            }
        )
    return deps


# 极简情感分析（内置词典），返回 -1..1
def _lexicon_sentiment(text: str, lang: str) -> Optional[float]:
    tokens = [t.lemma or t.text for t in tokenize(text, lang) if not _is_punct(t.text)]
    if not tokens:
        return None
    if lang == "zh":
        pos, neg = _ZH_POS, _ZH_NEG
    else:
        pos, neg = _EN_POS, _EN_NEG
    score = sum(1 for w in tokens if w in pos) - sum(1 for w in tokens if w in neg)
    return score / max(len(tokens), 1)


def sentiment(text: str, lang: Optional[str] = None) -> dict:
    """情感分析。优先 SnowNLP（中）/ VADER（英），回退到内置词典。"""
    lang = lang or detect_language(text)
    raw = None
    score = 0.0

    if lang == "zh":
        try:
            from snownlp import SnowNLP  # type: ignore

            raw = SnowNLP(text).sentiments  # 0..1
            score = raw * 2 - 1
        except Exception:
            lex = _lexicon_sentiment(text, "zh")
            if lex is not None:
                score = lex
                raw = (lex + 1) / 2
    else:
        try:
            import nltk  # type: ignore
            from nltk.sentiment.vader import SentimentIntensityAnalyzer  # type: ignore

            try:
                nltk.data.find("sentiment/vader_lexicon.zip")
            except LookupError:
                nltk.download("vader_lexicon", quiet=True)
            raw = SentimentIntensityAnalyzer().polarity_scores(text)["compound"]
            score = raw
        except Exception:
            lex = _lexicon_sentiment(text, "en")
            if lex is not None:
                score = lex
                raw = lex

    if score > 0.15:
        label = "正向"
    elif score < -0.15:
        label = "负向"
    else:
        label = "中性"
    return {"label": label, "score": round(score, 4), "raw": raw}


def analyze_syntax(text: str, lang: Optional[str] = None) -> SyntaxResult:
    """一次性执行全部句法 / 语义分析。"""
    lang = lang or detect_language(text)
    effective = lang if lang in ("en", "zh") else "en"
    return SyntaxResult(
        ner=named_entities(text, lang),
        keywords=extract_keywords(text, lang),
        dependencies=dependencies(text, lang),
        sentiment=sentiment(text, lang),
        pos_tags=[t.as_dict() for t in tokenize(text, lang)],
    )


# --------------------------------------------------------------------------- #
# 模块自检
# --------------------------------------------------------------------------- #


def selfcheck() -> dict:
    """返回各后端可用性，供界面提示。"""
    jieba, _ = _get_jieba()
    return {
        "jieba": bool(jieba),
        "spacy_en": bool(_get_spacy("en")),
        "spacy_zh": bool(_get_spacy("zh")),
        "snownlp": _try_import("snownlp"),
        "nltk": _try_import("nltk"),
        "wordcloud": _try_import("wordcloud"),
        "matplotlib": _try_import("matplotlib"),
    }


def _try_import(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    import json

    sample = "自然语言处理很有趣。I love natural language processing!"
    print(detect_language(sample))
    print(json.dumps(analyze_basic(sample).summary(), ensure_ascii=False))
