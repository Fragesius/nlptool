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

from core.log import logger

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

# 中文句末标点：。！？
# 英文句末标点：. ! ?

# 称谓缩写：后跟人名（大写字母开头）是正常的，不应切分
_TITLES = {"mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st"}

# 其他缩写：后跟小写字母不切分；后跟大写字母通常是真正句子边界
_OTHER_ABBREVIATIONS = {
    # 公司/组织
    "inc", "ltd", "corp", "co", "llc", "plc", "gmbh", "sa", "ag",
    # 常见缩写
    "vs", "etc", "approx", "no", "ave", "blvd", "dept",
    "fig", "vol", "pp", "et", "al", "eq", "ch",
    # 月份
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept",
    "oct", "nov", "dec",
}
_ABBREVIATIONS = _TITLES | _OTHER_ABBREVIATIONS

# 中文句末标点 + 英文句末标点（用于扫描）
_SENT_END_PUNCT = set("。！？!?\n")


def _is_abbreviation(text: str, dot_pos: int) -> bool:
    """判断 ``text[dot_pos]`` 处的句号是否属于缩写。

    规则：
    1. 句号前的单词（连续字母）在缩写列表中（如 ``Inc.``、``Mr.``、``Dr.``）
    2. 首字母缩写模式：句号前是单个大写字母，且该字母前还有 ``字母.`` 模式
       （如 ``U.S.A.`` 中的 ``U.``、``S.``、``A.``）
    3. 单字母缩写连续模式：句号前是单字母，且句号后紧跟 ``字母.`` 或前面有 ``字母.``
       （如 ``e.g.`` 中的 ``e.`` 后跟 ``g.``，或 ``g.`` 前面是 ``e.``）
    """
    # 向前扫描连续字母
    i = dot_pos - 1
    while i >= 0 and text[i].isalpha():
        i -= 1
    word = text[i + 1:dot_pos]
    if not word:
        return False

    # 规则 1：常见缩写词
    if word.lower() in _ABBREVIATIONS:
        return True

    if len(word) != 1:
        return False

    # 规则 2：单个大写字母（首字母缩写，如 U.S.A.）
    # 检查该字母前面是否也是 "字母." 模式（连续首字母缩写）
    if word.isupper():
        # 向前检查：word 前面是 "."，再前面是字母，再前面是 "." 或行首
        k = i  # word 开始位置 - 1（即 word 前一个字符）
        if k >= 0 and text[k] == ".":
            # 前面有句号，检查再前面是否为字母
            m = k - 1
            while m >= 0 and text[m].isalpha():
                m -= 1
            if k - 1 > m:  # 前面有字母
                return True
        # 也可能是第一个字母（如 "U.S.A." 的 "U"），后面跟 "S."
        # 检查后面是否为 "字母." 模式
        j = dot_pos + 1
        while j < len(text) and text[j] in " \t":
            j += 1
        if (j + 1 < len(text) and text[j].isalpha() and text[j].isupper()
                and text[j + 1] == "."):
            return True
        # 单个大写字母也可能是独立缩写（如 "U."），保守起见返回 True
        return True

    # 规则 3：单字母（小写），检查前后是否为 "字母." 模式（如 e.g.）
    # 检查后面是否为 "字母." 模式
    j = dot_pos + 1
    while j < len(text) and text[j] in " \t":
        j += 1
    if (j + 1 < len(text) and text[j].isalpha()
            and text[j + 1] == "."):
        return True
    # 检查前面是否为 "字母." 模式
    k = i  # word 前
    if k >= 0 and text[k] == ".":
        m = k - 1
        while m >= 0 and text[m].isalpha():
            m -= 1
        if k - 1 > m:
            return True

    return False


def _get_prev_word(text: str, dot_pos: int) -> str:
    """获取句号前的连续字母单词（原始大小写）。"""
    i = dot_pos - 1
    while i >= 0 and text[i].isalpha():
        i -= 1
    return text[i + 1:dot_pos]


def split_sentences(text: str) -> List[str]:
    """切分句子，兼顾中英文标点和常见缩写。

    与旧版纯正则不同，本实现用扫描器逐字符判断句号是否为真正的句子边界：
    - 中文句末标点（。！？）总是切分
    - 英文句号（.）切分，除非：
      * 属于称谓缩写（``Mr.``/``Dr.``/``Mrs.`` 等）：后跟人名（大写）不切分
      * 属于其他缩写（``Inc.``/``Ltd.``/``U.S.A.`` 等）且后跟小写字母：不切分
      * 后跟数字（小数/版本号，如 ``3.14``、``2.0.1``）：不切分
    - 换行符作为分隔符（保留段落结构）
    """
    text = text.strip()
    if not text:
        return []

    sents: List[str] = []
    start = 0
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\n":
            if i > start:
                seg = text[start:i].strip()
                if seg:
                    sents.append(seg)
            start = i + 1
            i += 1
            continue
        if c in "。！？!?":
            seg = text[start:i + 1].strip()
            if seg:
                sents.append(seg)
            start = i + 1
            i += 1
            continue
        if c == ".":
            # 先检查句号后是否紧跟数字（小数/版本号，如 3.14、2.0.1）
            j = i + 1
            while j < n and text[j] in " \t":
                j += 1
            next_char = text[j] if j < n else ""

            if next_char.isdigit():
                # 句号后跟数字，不切分（小数、版本号）
                i += 1
                continue

            # 检查是否为缩写
            if _is_abbreviation(text, i):
                prev_word_raw = _get_prev_word(text, i)
                prev_word = prev_word_raw.lower()
                is_title = prev_word in _TITLES
                # 称谓缩写（Mr./Dr./Mrs. 等）：后跟大写（人名）不切分
                if is_title:
                    i += 1
                    continue
                # 单字母大写缩写（如 U.S.A. 中的 U./S./A.）：
                # 若后跟 "字母." 模式（如 A. 后跟 B.），属于连续首字母缩写，不切分
                if len(prev_word_raw) == 1 and prev_word_raw.isupper():
                    # 检查后面是否为 "字母." 模式
                    k = i + 1
                    while k < n and text[k] in " \t":
                        k += 1
                    if (k + 1 < n and text[k].isalpha()
                            and text[k + 1] == "."):
                        i += 1
                        continue
                # 非称谓缩写（Inc./Ltd./U.S.A. 等）：
                #   - 后跟小写字母或标点：缩写内部，不切分
                #   - 后跟大写字母：通常是真正句子边界，切分
                if next_char and next_char.isupper():
                    # 缩写后跟大写：真正的句子边界
                    seg = text[start:i + 1].strip()
                    if seg:
                        sents.append(seg)
                    start = i + 1
                    i += 1
                    continue
                # 后跟小写或标点或行尾：不切分
                i += 1
                continue
            # 真正的句子边界
            seg = text[start:i + 1].strip()
            if seg:
                sents.append(seg)
            start = i + 1
            i += 1
            continue
        i += 1

    # 处理末尾剩余
    if start < n:
        seg = text[start:].strip()
        if seg:
            sents.append(seg)

    return sents


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
        except ImportError as e:
            logger.warning("jieba 未安装，中文分词将回退到字符切分: %s", e)
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
        except Exception as e:
            logger.warning("spaCy 模型 %s 加载失败: %s", model, e)
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
    # mixed：按 CJK / 拉丁片段分别处理（含数字）
    tokens: List[Token] = []
    # 用正则切出中文段、英文段与数字段
    for seg in re.findall(r"[一-鿿]+|[A-Za-z][A-Za-z\s.,;:!?'\"-]*|\d+(?:\.\d+)*", text):
        if _CJK_RE.search(seg):
            tokens.extend(tokenize_zh(seg))
        elif seg.strip().replace(".", "").isdigit():
            # 纯数字片段直接作为词元，避免被英文分词器丢弃
            tokens.append(Token(text=seg.strip(), pos="NUM", lemma=seg.strip(), lang="en"))
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
        char_count_no_space=len(re.sub(r"\s", "", text)),
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
    """依存句法分析（依赖 spaCy）。

    每个词条附带了 ``sent_id``（句子编号）和 ``sent_i``（句内序号），
    供可视化模块按句子分组绘制依存弧。

    双语处理：对中英混合文本，按句子语言分别使用 zh / en 模型，
    避免单一模型处理非目标语言时产生错误的依存关系
    （例如 zh 模型会把英文 "I" 误标为 compound:nn）。
    """
    lang = lang or detect_language(text)

    # 混合语言：按句子分别用对应模型处理
    if lang == "mixed":
        return _dependencies_mixed(text)

    nlp = _get_spacy(lang if lang in ("en", "zh") else "en")
    if not nlp:
        return []

    doc = nlp(text)
    # 为每个句子建立 token 索引映射（-> 句内序号）
    sent_boundaries: List[tuple] = []  # [(start_i, end_i), ...]
    for sent in doc.sents:
        sent_boundaries.append((sent.start, sent.end))

    deps: List[dict] = []
    for t in doc:
        if t.is_space:
            continue
        # 找到该 token 所属的句子 id 和句内序号
        sent_id = 0
        sent_i = 0
        for sid, (s_start, s_end) in enumerate(sent_boundaries):
            if s_start <= t.i < s_end:
                sent_id = sid
                sent_i = t.i - s_start
                break
        deps.append(
            {
                "text": t.text,
                "pos": t.pos_,
                "dep": t.dep_,
                "head_text": t.head.text,
                "head_pos": t.head.pos_,
                "head_i": t.head.i,        # head token 的全局序号
                "token_i": t.i,            # 当前 token 自身的全局序号
                "sent_id": sent_id,        # 句子编号
                "sent_i": sent_i,          # 句内序号
            }
        )
    return deps


def _dependencies_mixed(text: str) -> List[dict]:
    """处理混合语言文本：按句子语言分别使用对应 spaCy 模型。

    - 纯中文句 → zh 模型
    - 纯英文句 → en 模型
    - 句内仍混合（如「我用 Python 编程」）→ zh 模型（zh 处理混合句优于 en 处理中文）
    每个句子的 token_i / head_i 均为句内序号（从 0 开始），
    保证 ``_resolve_head_local`` 能在同一句内正确定位 head。
    """
    sents = split_sentences(text)
    if not sents:
        return []

    all_deps: List[dict] = []
    for sent_id, sent_text in enumerate(sents):
        sent_lang = detect_language(sent_text)
        if sent_lang == "mixed":
            # 句内混合：含 CJK 用 zh 模型
            sent_lang = "zh" if any("一" <= c <= "鿿" for c in sent_text) else "en"

        nlp = _get_spacy(sent_lang if sent_lang in ("en", "zh") else "en")
        if not nlp:
            continue

        doc = nlp(sent_text)
        for t in doc:
            if t.is_space:
                continue
            all_deps.append(
                {
                    "text": t.text,
                    "pos": t.pos_,
                    "dep": t.dep_,
                    "head_text": t.head.text,
                    "head_pos": t.head.pos_,
                    "head_i": t.head.i,    # 句内 head 序号
                    "token_i": t.i,        # 句内自身序号
                    "sent_id": sent_id,
                    "sent_i": t.i,         # 句内序号（单句处理时等于 t.i）
                }
            )
    return all_deps


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
                score = 0.0
                raw = 0.5  # 中性默认值，避免返回 None
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
            else:
                score = 0.0
                raw = 0.0  # 中性默认值，避免返回 None

    if score > 0.15:
        label = "正向"
    elif score < -0.15:
        label = "负向"
    else:
        label = "中性"
    return {"label": label, "score": round(score, 4), "raw": raw}


def analyze_syntax(text: str, lang: Optional[str] = None) -> SyntaxResult:
    """一次性执行全部句法 / 语义分析。

    性能优化：单语情况下对整段文本只调用 spaCy ``nlp(text)`` **一次**，
    从同一 ``Doc`` 提取 NER / 依存 / 分词，避免原路径中对同一段文本
    重复处理 3-4 次（spaCy 是最重的操作）。
    混合语言仍走原按句处理路径（每句语言不同，必须分别用对应模型）。
    """
    lang = lang or detect_language(text)

    # 混合语言：保持原路径（按句分别用对应模型）
    if lang == "mixed":
        return SyntaxResult(
            ner=named_entities(text, lang),
            keywords=extract_keywords(text, lang),
            dependencies=dependencies(text, lang),
            sentiment=sentiment(text, lang),
            pos_tags=[t.as_dict() for t in tokenize(text, lang)],
        )

    # 单语：只调用 spaCy 一次，复用 Doc 提取所有结构化数据
    effective = lang if lang in ("en", "zh") else "en"
    nlp = _get_spacy(effective)
    if nlp:
        doc = nlp(text)  # 唯一一次 spaCy 调用
        ner = _spacy_doc_to_ner(doc)
        deps = _spacy_doc_to_deps(doc)
        tokens = _spacy_doc_to_tokens(doc, effective)
    else:
        # spaCy 不可用：回退到 jieba/正则路径
        ner = []
        deps = []
        tokens = tokenize(text, lang)

    return SyntaxResult(
        ner=ner,
        keywords=extract_keywords(text, lang),
        dependencies=deps,
        sentiment=sentiment(text, lang),
        pos_tags=[t.as_dict() for t in tokens],
    )


# --------------------------------------------------------------------------- #
# spaCy Doc → 结构化数据（内部复用，避免重复 nlp 调用）
# --------------------------------------------------------------------------- #


def _spacy_doc_to_ner(doc) -> List[dict]:
    """从 spaCy ``Doc`` 提取命名实体。"""
    return [
        {"text": ent.text, "label": ent.label_,
         "start": ent.start_char, "end": ent.end_char}
        for ent in doc.ents
    ]


def _spacy_doc_to_deps(doc) -> List[dict]:
    """从 spaCy ``Doc`` 提取依存关系（含 sent_id / sent_i）。

    复刻 :func:`dependencies` 单语路径的逻辑，但不重新调用 ``nlp``。
    """
    sent_boundaries: List[tuple] = [(s.start, s.end) for s in doc.sents]
    deps: List[dict] = []
    for t in doc:
        if t.is_space:
            continue
        # 找到该 token 所属的句子 id 和句内序号
        sent_id = 0
        sent_i = 0
        for sid, (s_start, s_end) in enumerate(sent_boundaries):
            if s_start <= t.i < s_end:
                sent_id = sid
                sent_i = t.i - s_start
                break
        deps.append(
            {
                "text": t.text,
                "pos": t.pos_,
                "dep": t.dep_,
                "head_text": t.head.text,
                "head_pos": t.head.pos_,
                "head_i": t.head.i,
                "token_i": t.i,
                "sent_id": sent_id,
                "sent_i": sent_i,
            }
        )
    return deps


def _spacy_doc_to_tokens(doc, lang: str) -> List[Token]:
    """从 spaCy ``Doc`` 提取 :class:`Token` 列表。

    复刻 :func:`tokenize_en` 的 spaCy 路径，但不重新调用 ``nlp``。
    """
    stop_set = _ZH_STOP if lang == "zh" else _EN_STOP
    tokens: List[Token] = []
    for t in doc:
        if t.is_space:
            continue
        tokens.append(
            Token(
                text=t.text,
                pos=t.pos_,
                lemma=t.lemma_.lower(),
                is_stop=t.is_stop or t.text.lower() in stop_set,
                lang=lang,
            )
        )
    return tokens


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
