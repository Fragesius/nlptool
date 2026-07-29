"""语言指纹分析引擎（Linguistic Fingerprint）。

通过多维度特征比较文本 A 与嫌疑作者 B 及对照作者 C1-C3 的写作风格，
判断 A 是否更接近 B 的指纹。

特征维度（分维度加权余弦相似度）：
- 虚词频率         权重 0.30  （作者识别黄金标准）
- 标点使用模式      权重 0.15  （强作者信号）
- 词 bigram        权重 0.15  （短语风格）
- 词长分布          权重 0.10
- 句长均值与标准差  权重 0.10
- TTR（词汇丰富度） 权重 0.10
- 字符 4-gram      权重 0.05  （内容依赖，不可靠）
- Hapax 比例       权重 0.05

统计方法：分维度加权余弦相似度 + Wilcoxon 符号秩检验 + 置换检验 + Cohen's d

注意：旧版将全部特征拼接为一个向量，字 4-gram 占 100/213≈47%，
导致内容层面的偶然相似完全淹没风格层面的有效信号。
现已改为分维度加权计算，每个维度的贡献由其权重决定。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from core.analyzer import (  # type: ignore[import]
    Token,
    _is_punct,
    detect_language,
    split_sentences,
    tokenize,
)

# =============================================================================
# 扩充虚词列表（比 analyzer.py 中的 stop words 更全面）
# =============================================================================

# --- 中文虚词 (~260 词) ---
_ZH_FUNC_LIST = [
    # 代词
    "我", "你", "他", "她", "它", "我们", "你们", "他们", "她们", "它们",
    "自己", "别人", "大家", "本人", "彼此", "各自", "自身", "他人",
    "这", "那", "这些", "那些", "这里", "那里", "这边", "那边",
    "这么", "那么", "这样", "那样", "这个", "那个", "这次", "那次",
    "什么", "谁", "哪", "怎么", "怎么样", "多少", "几", "哪边",
    # 介词
    "在", "从", "到", "向", "对", "给", "为", "跟", "和", "与",
    "同", "比", "被", "把", "将", "由", "按", "按照", "以",
    "除了", "关于", "对于", "根据", "经过", "通过", "沿着", "顺着",
    "朝", "往", "当", "趁", "自从", "为了", "因为", "由于",
    # 连词
    "和", "与", "及", "以及", "或", "或者", "但", "但是", "而",
    "而且", "并且", "然而", "虽然", "因为", "所以", "因此",
    "如果", "假如", "即使", "尽管", "不管", "无论", "除非",
    "只要", "只有", "不但", "不仅", "还", "也", "又",
    "就", "才", "便", "则", "于是", "然后", "接着", "之后",
    "要不", "要不然", "何况", "况且", "至于",
    # 助词/语气词
    "的", "地", "得", "了", "着", "过",
    "吗", "呢", "吧", "啊", "呀", "嘛", "呗", "喽", "嗯", "哦",
    "之", "所", "等", "而言", "来说",
    # 副词
    "很", "都", "就", "才", "刚", "已经", "曾经", "正在", "将要",
    "常常", "总是", "一直", "始终", "一向", "从来", "永远",
    "终于", "忽然", "突然", "立刻", "马上", "渐渐", "逐渐",
    "重新", "再", "又", "也", "还", "另外",
    "大约", "大概", "几乎", "简直", "尤其", "特别",
    "不", "没", "没有", "未", "别", "不要", "不必",
    # 量词
    "个", "种", "次", "回", "遍", "趟", "张", "条", "件",
    "本", "支", "只", "块", "片", "些", "点", "段",
    # 数词/时间词
    "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
    "百", "千", "万", "第一", "第二", "第三",
    "每", "各", "某", "任何", "所有",
    "今天", "明天", "昨天", "现在", "以前", "以后",
    "上", "下", "前", "后", "中", "内", "外", "里",
    "年", "月", "日", "时", "分", "秒",
]

_ZH_FUNC_SET = frozenset(_ZH_FUNC_LIST)

# --- 英文虚词 (~300 词) ---
_EN_FUNC_LIST = [
    # Pronouns
    "i", "me", "my", "mine", "myself",
    "you", "your", "yours", "yourself", "yourselves",
    "he", "him", "his", "himself",
    "she", "her", "hers", "herself",
    "it", "its", "itself",
    "we", "us", "our", "ours", "ourselves",
    "they", "them", "their", "theirs", "themselves",
    "who", "whom", "whose", "which", "what", "whatever",
    # Determiners
    "the", "a", "an",
    "this", "that", "these", "those",
    "each", "every", "all", "both", "some", "any",
    "no", "none", "few", "many", "much", "several",
    "most", "more", "less", "such", "other", "another",
    # Prepositions
    "in", "on", "at", "to", "for", "from", "of", "with", "by",
    "about", "into", "onto", "upon", "through", "throughout",
    "during", "before", "after", "above", "below",
    "between", "among", "under", "over", "against",
    "within", "without", "near", "behind", "across",
    "along", "around", "beyond", "up", "down", "off", "out",
    "toward", "towards", "until", "till", "since", "despite",
    "beside", "besides", "except", "including",
    # Conjunctions
    "and", "but", "or", "nor", "for", "so", "yet",
    "although", "though", "because", "since", "while",
    "if", "when", "where", "unless", "until",
    "whereas", "whether", "than", "as", "that",
    "once", "after", "before", "either", "neither",
    # Auxiliaries / Modals
    "be", "am", "is", "are", "was", "were", "being", "been",
    "have", "has", "had", "having",
    "do", "does", "did", "doing",
    "will", "would", "shall", "should",
    "can", "could", "may", "might", "must", "ought",
    # Adverbs / Negation
    "not", "no", "never", "ever", "always", "often",
    "sometimes", "usually", "rarely", "seldom",
    "just", "already", "yet", "still", "almost",
    "also", "too", "very", "really", "quite", "rather",
    "only", "even", "perhaps", "maybe", "probably",
    "certainly", "indeed", "however", "therefore",
    "thus", "moreover", "furthermore", "nevertheless",
    "then", "now", "here", "there", "so",
    # Numbers (common)
    "one", "two", "three", "four", "five",
    "six", "seven", "eight", "nine", "ten",
    "first", "second", "third", "last",
]

_EN_FUNC_SET = frozenset(_EN_FUNC_LIST)


def get_func_words(lang: str) -> frozenset:
    """返回指定语言的虚词集合。"""
    return _ZH_FUNC_SET if lang == "zh" else _EN_FUNC_SET


# =============================================================================
# 标点集合
# =============================================================================

_ZH_PUNCT = "，。！？、；：""''（）《》【】…—～·「」『』﹁﹂"
_EN_PUNCT = ",.!?;:\"'()-—…"

_PUNCT_MAP = {
    "zh": _ZH_PUNCT,
    "en": _EN_PUNCT,
}


def get_punct_set(lang: str) -> str:
    """返回指定语言关注的标点字符集。"""
    return _PUNCT_MAP.get(lang, _ZH_PUNCT)


# =============================================================================
# 数据结构
# =============================================================================


@dataclass
class SegmentInfo:
    """一个文本片段。"""

    text: str
    segment_index: int
    char_count: int
    lang: str  # "zh" or "en"


@dataclass
class FeatureVector:
    """单片段特征向量。"""

    word_length_dist: List[float] = field(default_factory=list)
    function_word_freq: List[float] = field(default_factory=list)
    char_ngrams: List[float] = field(default_factory=list)
    word_bigrams: List[float] = field(default_factory=list)
    sent_len_mean: float = 0.0
    sent_len_std: float = 0.0
    punct_dist: List[float] = field(default_factory=list)
    ttr: float = 0.0           # Type-Token Ratio，词汇丰富度
    hapax_ratio: float = 0.0   # Hapax Legomena 比例（仅出现一次的词的占比）
    raw_vector: List[float] = field(default_factory=list)
    segment_index: int = 0


# ── 分维度权重 ──────────────────────────────────────────────
# 每个特征维度在作者识别中的重要性不同。
# 虚词频率是作者的"DNA"，字 4-gram 则高度依赖内容（题材、场景）。
# 拼接为一个向量时，维数大的特征天然占优——这正是错判的根源。
# 改为分维度余弦相似度的加权平均，每个维度贡献由权重决定。
FEATURE_WEIGHTS = {
    "word_length_dist":   0.10,   # 词长分布
    "function_word_freq": 0.30,   # 虚词频率 — 作者识别黄金标准
    "char_ngrams":        0.05,   # 字 4-gram — 内容依赖，低权重
    "word_bigrams":       0.15,   # 词 bigram — 短语风格
    "sentence_stats":     0.10,   # 句长均值+标准差
    "punct_dist":         0.15,   # 标点模式 — 强作者信号
    "ttr":                0.10,   # 词汇丰富度
    "hapax_ratio":        0.05,   # 罕见词比例
}
# 确保权重和为 1.0
assert abs(sum(FEATURE_WEIGHTS.values()) - 1.0) < 1e-9, f"权重和 != 1.0: {sum(FEATURE_WEIGHTS.values())}"


@dataclass
class AuthorProfile:
    """一个作者（或文本 A）的完整画像。"""

    author_label: str
    segments: List[SegmentInfo] = field(default_factory=list)
    feature_vectors: List[FeatureVector] = field(default_factory=list)
    aggregate_vector: List[float] = field(default_factory=list)


@dataclass
class SimilarityResult:
    """A 与某个参考作者的相似度结果。"""

    ref_label: str
    segment_similarities: List[float] = field(default_factory=list)
    mean_similarity: float = 0.0
    std_similarity: float = 0.0


@dataclass
class FingerprintResult:
    """语言指纹分析完整结果。"""

    suspect_profile: AuthorProfile = field(default_factory=lambda: AuthorProfile("A"))
    suspect_author_profile: AuthorProfile = field(
        default_factory=lambda: AuthorProfile("B")
    )
    control_profiles: List[AuthorProfile] = field(default_factory=list)
    similarity_to_b: SimilarityResult = field(
        default_factory=lambda: SimilarityResult("B")
    )
    similarity_to_controls: List[SimilarityResult] = field(default_factory=list)
    p_value_wilcoxon: float = 1.0
    p_value_permutation: float = 1.0
    cohens_d: float = 0.0
    verdict: str = "不确定"

    def summary(self) -> str:
        lines = []
        sep = "─" * 56
        lines.append(sep)
        lines.append("  语言指纹分析报告")
        lines.append(sep)

        b_sim = self.similarity_to_b
        lines.append(f"\n  A ↔ 嫌疑作者 B    相似度: {b_sim.mean_similarity:.4f} ± {b_sim.std_similarity:.4f}")
        for sc in self.similarity_to_controls:
            lines.append(f"  A ↔ 对照 {sc.ref_label}        相似度: {sc.mean_similarity:.4f} ± {sc.std_similarity:.4f}")

        lines.append(f"\n  Wilcoxon 符号秩检验  p = {self.p_value_wilcoxon:.4f}")
        lines.append(f"  置换检验 (10k)       p = {self.p_value_permutation:.4f}")
        lines.append(f"  Cohen's d            d = {self.cohens_d:.3f}")

        # 效应量解释
        d = abs(self.cohens_d)
        if d < 0.2:
            d_note = "可忽略"
        elif d < 0.5:
            d_note = "小效应"
        elif d < 0.8:
            d_note = "中效应"
        else:
            d_note = "大效应"
        lines.append(f"  效应量解释: {d_note}")

        lines.append(f"\n  🏷 结论: {self.verdict}")
        lines.append(sep)
        return "\n".join(lines)

    def verdict_detail(self) -> str:
        return (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠ 注意事项：\n"
            "  · 本分析仅基于文本统计特征，不构成法律证据。\n"
            "  · 样本量越大、对照作者越匹配，结论越可靠。\n"
            "  · 建议结合其他证据综合判断。\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )


# =============================================================================
# 文本分段
# =============================================================================


def segment_text(
    text: str, lang: str, segment_size: int = 1000
) -> List[SegmentInfo]:
    """将文本按约 segment_size 字符分段，尊重句子边界。

    Args:
        text: 输入文本。
        lang: 语言代码 ("zh" / "en")。
        segment_size: 每段目标字符数（英文按词数×3 估算）。

    Returns:
        SegmentInfo 列表。文本太短返回空列表。
    """
    sentences = split_sentences(text)
    if not sentences:
        return []

    segments: List[SegmentInfo] = []
    buffer: List[str] = []
    char_acc = 0
    seg_idx = 0

    for sent in sentences:
        if lang == "en":
            # 英文按词计数，1 词 ≈ 3 字符
            sent_weight = len(sent.split()) * 3
        else:
            sent_weight = _non_space_len(sent)

        buffer.append(sent)
        char_acc += sent_weight

        if char_acc >= segment_size and buffer:
            seg_text = "".join(buffer)
            segments.append(
                SegmentInfo(
                    text=seg_text,
                    segment_index=seg_idx,
                    char_count=_non_space_len(seg_text),
                    lang=lang,
                )
            )
            seg_idx += 1
            buffer.clear()
            char_acc = 0

    # 残余句子：若足够大则独立成段，否则合并到最后一段
    if buffer:
        seg_text = "".join(buffer)
        if segments and _non_space_len(seg_text) < segment_size // 3:
            # 合并到最后一段
            prev = segments[-1]
            merged = prev.text + seg_text
            segments[-1] = SegmentInfo(
                text=merged,
                segment_index=prev.segment_index,
                char_count=_non_space_len(merged),
                lang=lang,
            )
        else:
            segments.append(
                SegmentInfo(
                    text=seg_text,
                    segment_index=seg_idx,
                    char_count=_non_space_len(seg_text),
                    lang=lang,
                )
            )

    return segments


def _non_space_len(text: str) -> int:
    """不包含空白和换行的字符数。"""
    return len(text.replace(" ", "").replace("\n", "").replace("\r", ""))


# =============================================================================
# 特征提取
# =============================================================================


def _tokens_from_text(text: str, lang: str) -> List[Token]:
    """对片段文本分词。"""
    return tokenize(text, lang)


def extract_word_length_dist(tokens: List[Token], lang: str) -> List[float]:
    """词长分布（归一化）。"""
    lengths = []
    for t in tokens:
        if _is_punct(t.text) or not t.text.strip():
            continue
        wlen = len(t.text)
        lengths.append(wlen)

    if not lengths:
        return []  # 调用方会填充

    if lang == "zh":
        bins = [1, 2, 3, 4]
        hist = [0.0, 0.0, 0.0, 0.0]
        for wl in lengths:
            if wl >= 4:
                hist[3] += 1
            else:
                hist[wl - 1] += 1
    else:
        bins_count = 10
        hist = [0.0] * bins_count
        for wl in lengths:
            idx = min(wl - 1, bins_count - 1)
            hist[idx] += 1

    total = sum(hist)
    if total > 0:
        hist = [v / total for v in hist]
    return hist


def extract_function_word_freq(
    tokens: List[Token], lang: str, global_vocab: List[str]
) -> List[float]:
    """虚词频率（按 global_vocab 顺序，归一化）。"""
    func_set = get_func_words(lang)
    counts: Dict[str, int] = {}
    total_func = 0
    for t in tokens:
        w = t.text.lower() if lang == "en" else t.text
        if w in func_set:
            counts[w] = counts.get(w, 0) + 1
            total_func += 1

    result = []
    for w in global_vocab:
        if total_func > 0:
            result.append(counts.get(w, 0) / total_func)
        else:
            result.append(0.0)
    return result


def _clean_for_char_ngram(text: str, lang: str) -> str:
    """去掉标点和空白，英文转小写，返回可用于字级 n-gram 的字符串。"""
    if lang == "en":
        # 只保留 a-z 字母
        return "".join(ch.lower() for ch in text if ch.isalpha())
    else:
        # 中文：去标点和空白
        punct = set(_ZH_PUNCT + " \n\r\t")
        return "".join(ch for ch in text if ch not in punct)


def extract_char_ngrams(
    text: str, n: int, top_n: int, lang: str, global_vocab: List[str]
) -> List[float]:
    """字符级 n-gram 频率（按 global_vocab 顺序）。"""
    clean = _clean_for_char_ngram(text, lang)
    if len(clean) < n:
        return [0.0] * len(global_vocab) if global_vocab else []

    counts: Dict[str, int] = {}
    total = 0
    for i in range(len(clean) - n + 1):
        gram = clean[i : i + n]
        counts[gram] = counts.get(gram, 0) + 1
        total += 1

    result = []
    for g in global_vocab:
        result.append(counts.get(g, 0) / total if total > 0 else 0.0)
    return result


def extract_word_bigrams(
    tokens: List[Token], lang: str, global_vocab: List[str]
) -> List[float]:
    """词级 bigram 频率（按 global_vocab 顺序，归一化）。"""
    # 过滤掉标点的词序列
    words = []
    for t in tokens:
        if _is_punct(t.text) or not t.text.strip():
            continue
        w = t.text.lower() if lang == "en" else t.text
        words.append(w)

    if len(words) < 2:
        return [0.0] * len(global_vocab) if global_vocab else []

    counts: Dict[str, int] = {}
    total = 0
    for i in range(len(words) - 1):
        bg = words[i] + "|" + words[i + 1]
        counts[bg] = counts.get(bg, 0) + 1
        total += 1

    result = []
    for bg in global_vocab:
        result.append(counts.get(bg, 0) / total if total > 0 else 0.0)
    return result


def extract_sentence_stats(text: str, lang: str) -> Tuple[float, float]:
    """句长均值与标准差（按词数计）。"""
    sents = split_sentences(text)
    if not sents:
        return (0.0, 0.0)

    lengths = []
    for sent in sents:
        tokens = tokenize(sent, lang)
        word_count = sum(1 for t in tokens if not _is_punct(t.text) and t.text.strip())
        if word_count > 0:
            lengths.append(word_count)

    if not lengths:
        return (0.0, 0.0)

    n = len(lengths)
    mean = sum(lengths) / n
    if n > 1:
        variance = sum((x - mean) ** 2 for x in lengths) / (n - 1)
        std = math.sqrt(variance)
    else:
        std = 0.0
    return (mean, std)


def extract_punct_dist(text: str, lang: str, global_vocab: List[str]) -> List[float]:
    """标点分布频率（按 global_vocab 顺序）。"""
    punct_set = set(get_punct_set(lang))
    counts: Dict[str, int] = {}
    total = 0
    for ch in text:
        if ch in punct_set:
            counts[ch] = counts.get(ch, 0) + 1
            total += 1

    result = []
    for p in global_vocab:
        result.append(counts.get(p, 0) / total if total > 0 else 0.0)
    return result


def extract_ttr_hapax(tokens: List[Token], lang: str) -> Tuple[float, float]:
    """计算 TTR（Type-Token Ratio）和 Hapax Legomena 比例。

    TTR = 不重复词数 / 总词数，衡量词汇丰富度。
    Hapax = 仅出现一次的词数 / 总词数，衡量罕见词使用倾向。

    这两个特征是经典的作者识别指标，与内容主题相对独立。
    """
    words = []
    for t in tokens:
        if _is_punct(t.text) or not t.text.strip():
            continue
        w = t.text.lower() if lang == "en" else t.text
        words.append(w)

    if not words:
        return (0.0, 0.0)

    total = len(words)
    freq: Dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1

    types = len(freq)
    ttr = types / total

    hapax_count = sum(1 for v in freq.values() if v == 1)
    hapax_ratio = hapax_count / total

    return (ttr, hapax_ratio)


# =============================================================================
# 全局词汇表构建
# =============================================================================


def build_global_vocab(
    texts: List[str],
    lang: str,
    top_n_func: int = 50,
    top_n_ngram: int = 100,
    top_n_bigram: int = 50,
    top_n_punct: int = 20,
) -> dict:
    """扫描所有文本，建立全局虚词 / n-gram / bigram / 标点词汇表。

    确保每个片段的特征向量维度一致。
    """
    # --- 虚词：取全局频率最高的 top_n_func 个 ---
    func_set = get_func_words(lang)
    func_counts: Dict[str, int] = {}
    for text in texts:
        tokens = tokenize(text, lang)
        for t in tokens:
            w = t.text.lower() if lang == "en" else t.text
            if w in func_set:
                func_counts[w] = func_counts.get(w, 0) + 1
    sorted_func = sorted(func_counts.items(), key=lambda x: -x[1])
    func_vocab = [w for w, _ in sorted_func[:top_n_func]]

    # --- 字符 n-gram：全局频率最高的 top_n_ngram 个 ---
    gram_counts: Dict[str, int] = {}
    n = 4
    for text in texts:
        clean = _clean_for_char_ngram(text, lang)
        for i in range(len(clean) - n + 1):
            gram = clean[i : i + n]
            gram_counts[gram] = gram_counts.get(gram, 0) + 1
    sorted_grams = sorted(gram_counts.items(), key=lambda x: -x[1])
    gram_vocab = [g for g, _ in sorted_grams[:top_n_ngram]]

    # --- 词 bigram：全局频率最高的 top_n_bigram 个 ---
    bg_counts: Dict[str, int] = {}
    for text in texts:
        tokens = tokenize(text, lang)
        words = []
        for t in tokens:
            if _is_punct(t.text) or not t.text.strip():
                continue
            w = t.text.lower() if lang == "en" else t.text
            words.append(w)
        for i in range(len(words) - 1):
            bg = words[i] + "|" + words[i + 1]
            bg_counts[bg] = bg_counts.get(bg, 0) + 1
    sorted_bg = sorted(bg_counts.items(), key=lambda x: -x[1])
    bg_vocab = [b for b, _ in sorted_bg[:top_n_bigram]]

    # --- 标点 ---
    punct_set = set(get_punct_set(lang))
    punct_counts: Dict[str, int] = {}
    for text in texts:
        for ch in text:
            if ch in punct_set:
                punct_counts[ch] = punct_counts.get(ch, 0) + 1
    sorted_punct = sorted(punct_counts.items(), key=lambda x: -x[1])
    punct_vocab = [p for p, _ in sorted_punct[:top_n_punct]]

    return {
        "func": func_vocab,
        "char_ngram": gram_vocab,
        "word_bigram": bg_vocab,
        "punct": punct_vocab,
    }


# =============================================================================
# 特征提取入口
# =============================================================================


def extract_features(segment: SegmentInfo, global_vocab: dict) -> FeatureVector:
    """对单个片段提取全部特征。"""
    tokens = _tokens_from_text(segment.text, segment.lang)
    lang = segment.lang

    wld = extract_word_length_dist(tokens, lang)
    fwf = extract_function_word_freq(tokens, lang, global_vocab.get("func", []))
    cng = extract_char_ngrams(segment.text, 4, 100, lang, global_vocab.get("char_ngram", []))
    wbg = extract_word_bigrams(tokens, lang, global_vocab.get("word_bigram", []))
    sm, ss = extract_sentence_stats(segment.text, lang)
    pct = extract_punct_dist(segment.text, lang, global_vocab.get("punct", []))
    ttr, hapax = extract_ttr_hapax(tokens, lang)

    fv = FeatureVector(
        word_length_dist=wld,
        function_word_freq=fwf,
        char_ngrams=cng,
        word_bigrams=wbg,
        sent_len_mean=sm,
        sent_len_std=ss,
        punct_dist=pct,
        ttr=ttr,
        hapax_ratio=hapax,
        segment_index=segment.segment_index,
    )
    fv.raw_vector = _flatten_and_normalize(fv)
    return fv


def _flatten_and_normalize(fv: FeatureVector) -> List[float]:
    """将 FeatureVector 的各维度拼接为单个向量并 L2 归一化。

    保留此函数用于向后兼容（build_aggregate_vector 仍用 raw_vector）。
    核心相似度计算已改用分维度加权方法，不再依赖此拼接向量。
    """
    parts: List[float] = []
    parts.extend(fv.word_length_dist)
    parts.extend(fv.function_word_freq)
    parts.extend(fv.char_ngrams)
    parts.extend(fv.word_bigrams)
    parts.append(fv.sent_len_mean)
    parts.append(fv.sent_len_std)
    parts.extend(fv.punct_dist)
    parts.append(fv.ttr)
    parts.append(fv.hapax_ratio)

    norm = math.sqrt(sum(v * v for v in parts))
    if norm > 0:
        return [v / norm for v in parts]
    return parts


def build_aggregate_vector(vectors: List[FeatureVector]) -> List[float]:
    """多个片段向量的均值，L2 归一化。"""
    if not vectors:
        return []
    n = len(vectors)
    dim = len(vectors[0].raw_vector)
    avg = [0.0] * dim
    for vec in vectors:
        for i, v in enumerate(vec.raw_vector):
            avg[i] += v / n
    norm = math.sqrt(sum(v * v for v in avg))
    if norm > 0:
        avg = [v / norm for v in avg]
    return avg


# =============================================================================
# 相似度计算
# =============================================================================


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """余弦相似度。向量为零则返回 0。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _scalar_similarity(a: float, b: float) -> float:
    """两个标量值的相似度：1 - 归一化绝对差。

    当两个值相等时为 1.0，差异增大时趋近 0。
    """
    denom = max(abs(a), abs(b))
    if denom < 1e-12:
        return 1.0  # 两个都接近 0，视为相同
    diff = abs(a - b) / denom
    return max(0.0, 1.0 - diff)


def weighted_cosine_similarity(fv_a: FeatureVector, fv_b: FeatureVector) -> float:
    """分维度加权余弦相似度。

    对每个特征维度分别计算余弦相似度（标量用 _scalar_similarity），
    再按 FEATURE_WEIGHTS 做加权平均。

    这解决了旧版"拼接向量"的核心缺陷：字 4-gram 占 100 维，
    虚词频率占 50 维，拼接后 4-gram 天然主导结果。
    现在每个维度的贡献由权重决定，与维度大小无关。
    """
    scores: Dict[str, float] = {}

    # ── 辅助：余弦相似度 + 空向量 fallback ──
    # 如果某一方向量为空（文本太短导致该维度无数据），cosine 会返回 0.0，
    # 但 0 意味着"完全不相似"，会不公平地拉低总分。
    # 无数据时应给中性分 0.5，既不支持也不反对。
    # 注意：两个非空向量正交（cos=0）是真实的"不相似"信号，不应给中性分。
    def _cos_or_neutral(a_vec: List[float], b_vec: List[float]) -> float:
        if not a_vec or not b_vec:
            return 0.5
        return cosine_similarity(a_vec, b_vec)

    # 1. 词长分布
    scores["word_length_dist"] = _cos_or_neutral(
        fv_a.word_length_dist, fv_b.word_length_dist
    )

    # 2. 虚词频率 — 最重要的维度
    scores["function_word_freq"] = _cos_or_neutral(
        fv_a.function_word_freq, fv_b.function_word_freq
    )

    # 3. 字 4-gram — 低权重，仅作辅助
    scores["char_ngrams"] = _cos_or_neutral(
        fv_a.char_ngrams, fv_b.char_ngrams
    )

    # 4. 词 bigram
    scores["word_bigrams"] = _cos_or_neutral(
        fv_a.word_bigrams, fv_b.word_bigrams
    )

    # 5. 句长统计 — 两个标量分别比较再取均值
    sl_mean_sim = _scalar_similarity(fv_a.sent_len_mean, fv_b.sent_len_mean)
    sl_std_sim = _scalar_similarity(fv_a.sent_len_std, fv_b.sent_len_std)
    scores["sentence_stats"] = (sl_mean_sim + sl_std_sim) / 2.0

    # 6. 标点分布
    scores["punct_dist"] = _cos_or_neutral(
        fv_a.punct_dist, fv_b.punct_dist
    )

    # 7. TTR（词汇丰富度）
    scores["ttr"] = _scalar_similarity(fv_a.ttr, fv_b.ttr)

    # 8. Hapax 比例
    scores["hapax_ratio"] = _scalar_similarity(fv_a.hapax_ratio, fv_b.hapax_ratio)

    # 加权平均
    total = 0.0
    for key, weight in FEATURE_WEIGHTS.items():
        total += weight * scores.get(key, 0.0)

    return total


def _compute_similarities(
    profile_a: AuthorProfile, profile_ref: AuthorProfile
) -> SimilarityResult:
    """计算 profile_a 的各片段与 profile_ref 的聚合 FeatureVector 的相似度。

    使用分维度加权余弦相似度，替代旧版的拼接向量方法。
    """
    ref_fvs = profile_ref.feature_vectors
    if not ref_fvs:
        return SimilarityResult(ref_label=profile_ref.author_label)

    # 构建 ref 的"聚合 FeatureVector"：每个维度取各片段的均值
    ref_agg = _build_aggregate_feature_vector(ref_fvs)

    sims = []
    for fv in profile_a.feature_vectors:
        sim = weighted_cosine_similarity(fv, ref_agg)
        sims.append(sim)

    if sims:
        mean_s = sum(sims) / len(sims)
        var_s = sum((s - mean_s) ** 2 for s in sims) / len(sims)
    else:
        mean_s = 0.0
        var_s = 0.0

    return SimilarityResult(
        ref_label=profile_ref.author_label,
        segment_similarities=sims,
        mean_similarity=mean_s,
        std_similarity=math.sqrt(var_s),
    )


def _build_aggregate_feature_vector(fvs: List[FeatureVector]) -> FeatureVector:
    """从多个片段 FeatureVector 构建聚合向量（各维度均值）。"""
    if not fvs:
        return FeatureVector()

    n = len(fvs)

    # 向量维度取均值
    def _mean_vec(vecs: List[List[float]]) -> List[float]:
        if not vecs or not vecs[0]:
            return []
        dim = len(vecs[0])
        return [sum(v[i] for v in vecs) / n for i in range(dim)]

    return FeatureVector(
        word_length_dist=_mean_vec([fv.word_length_dist for fv in fvs]),
        function_word_freq=_mean_vec([fv.function_word_freq for fv in fvs]),
        char_ngrams=_mean_vec([fv.char_ngrams for fv in fvs]),
        word_bigrams=_mean_vec([fv.word_bigrams for fv in fvs]),
        sent_len_mean=sum(fv.sent_len_mean for fv in fvs) / n,
        sent_len_std=sum(fv.sent_len_std for fv in fvs) / n,
        punct_dist=_mean_vec([fv.punct_dist for fv in fvs]),
        ttr=sum(fv.ttr for fv in fvs) / n,
        hapax_ratio=sum(fv.hapax_ratio for fv in fvs) / n,
        segment_index=-1,
    )


# =============================================================================
# 统计检验（纯 Python，无 scipy 依赖）
# =============================================================================


def _erf(x: float) -> float:
    """误差函数近似（Abramowitz & Stegun 7.1.26）。"""
    sign = 1 if x >= 0 else -1
    x = abs(x)
    a1, a2, a3, a4, a5 = 0.254829592, -0.284496736, 1.421413741, -1.453152027, 1.061405429
    p = 0.3275911
    t = 1.0 / (1.0 + p * x)
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x)
    return sign * y


def _normal_cdf(x: float) -> float:
    """标准正态分布的 CDF。"""
    return 0.5 * (1.0 + _erf(x / math.sqrt(2.0)))


def _normal_sf(x: float) -> float:
    """标准正态分布的生存函数（1 - CDF）。"""
    return 1.0 - _normal_cdf(x)


def wilcoxon_signed_rank_test(differences: List[float]) -> float:
    """Wilcoxon 符号秩检验（双侧），返回 p-value。

    Args:
        differences: 配对观测值的差值列表 (d_i)。

    Returns:
        p-value（双侧）。
    """
    # 移除差值为零的对
    diffs = [d for d in differences if d != 0.0]
    n = len(diffs)
    if n < 3:
        return 1.0  # 样本量太小，无法拒绝 H0

    # 按绝对值排序并赋秩（平均秩处理平局）
    indexed = [(abs(d), i, d > 0) for i, d in enumerate(diffs)]
    indexed.sort(key=lambda x: x[0])

    ranks = [0.0] * n
    j = 0
    while j < n:
        k = j
        while k < n and indexed[k][0] == indexed[j][0]:
            k += 1
        avg_rank = (j + k + 2) / 2.0  # 1-indexed ranks averaged
        for m in range(j, k):
            ranks[indexed[m][1]] = avg_rank
        j = k

    w_pos = sum(r for r, (_, _, positive) in zip(ranks, indexed) if positive)
    w_neg = sum(r for r, (_, _, positive) in zip(ranks, indexed) if not positive)
    t_stat = min(w_pos, w_neg)

    # 正态近似
    expected = n * (n + 1) / 4.0
    std = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0)

    if std < 1e-12:
        return 1.0

    z = (t_stat - expected) / std

    # 双侧 p-value：2 * (1 - Φ(|z|))
    # 注意：必须用 |z|，否则当 t_stat > expected（反向偏离）时会得到 p > 1
    p = 2.0 * _normal_sf(abs(z))
    return min(max(p, 0.0), 1.0)


def permutation_test(
    a_vs_b: List[float],
    a_vs_controls: List[float],
    n_iter: int = 10000,
    seed: int = 42,
) -> float:
    """置换检验：H0 为 B 与 controls 相似度相同。

    Args:
        a_vs_b: A 各片段与 B 的相似度列表。
        a_vs_controls: A 各片段与 controls（合并）的相似度列表。
        n_iter: 置换次数。
        seed: 随机种子。

    Returns:
        单侧 p-value。
    """
    rng = random.Random(seed)
    all_vals = list(a_vs_b) + list(a_vs_controls)
    n_b = len(a_vs_b)
    if n_b == 0 or len(a_vs_controls) == 0:
        return 1.0

    obs_b = sum(a_vs_b) / n_b
    obs_c = sum(a_vs_controls) / len(a_vs_controls)
    obs_diff = obs_b - obs_c

    count = 0
    for _ in range(n_iter):
        rng.shuffle(all_vals)
        perm_b = sum(all_vals[:n_b]) / n_b
        perm_c = sum(all_vals[n_b:]) / len(all_vals[n_b:])
        if perm_b - perm_c >= obs_diff:
            count += 1

    return (count + 1) / (n_iter + 1)


def cohens_d(
    mean_a: float, mean_b: float, std_a: float, std_b: float,
    n_a: int = 0, n_b: int = 0,
) -> float:
    """Cohen's d 效应量。

    当 n_a, n_b > 1 时使用样本量加权的合并方差（标准 Cohen's d），
    否则退化为简单平均（向后兼容）。
    """
    if n_a > 1 and n_b > 1:
        pooled_var = ((n_a - 1) * std_a**2 + (n_b - 1) * std_b**2) / (n_a + n_b - 2)
    else:
        pooled_var = (std_a**2 + std_b**2) / 2.0
    if pooled_var < 1e-12:
        return 0.0
    return (mean_a - mean_b) / math.sqrt(pooled_var)


# =============================================================================
# 主入口
# =============================================================================


def analyze_fingerprint(
    suspect_text: str,
    suspect_author_text: str,
    control_texts: List[str],
    lang: Optional[str] = None,
) -> FingerprintResult:
    """运行完整的语言指纹分析。

    Args:
        suspect_text: 可疑文本 A。
        suspect_author_text: 嫌疑作者已知文本 B。
        control_texts: 对照作者文本列表（1-3 个）。
        lang: 语言代码，None 则自动检测。

    Returns:
        FingerprintResult。

    Raises:
        ValueError: 输入不符合要求。
    """
    # --- 1. 输入验证 ---
    a_len = _non_space_len(suspect_text)
    if a_len < 3000:
        raise ValueError(
            f"可疑文本 A 仅 {a_len} 字符，需要至少 3000 字符。"
        )
    if not suspect_author_text.strip():
        raise ValueError("嫌疑作者 B 的文本不能为空。")
    controls = [c for c in control_texts if c.strip()]
    if not controls:
        raise ValueError("至少需要 1 个对照作者文本。")
    if len(controls) > 3:
        controls = controls[:3]  # 静默截断

    # --- 2. 语言检测 ---
    if lang is None:
        lang = detect_language(suspect_text)
    if lang == "mixed":
        raise ValueError(
            "不支持中英混合文本进行语言指纹分析，请提供纯中文或纯英文文本。"
        )
    all_texts = [suspect_text, suspect_author_text] + controls
    # 检查所有文本语言一致性：某文本检测到不同语言（且非 mixed）时直接报错，
    # 否则后续 tokenize / 虚词集合会全部走错路径，特征向量接近全零。
    for txt in all_texts:
        txt_lang = detect_language(txt)
        if txt_lang != lang and txt_lang != "mixed":
            raise ValueError(
                f"文本语言不一致：期望 {lang}，但检测到 {txt_lang}。"
                f"请确保 A、B 及所有对照作者使用同一种语言。"
            )

    # --- 3. 构建全局词汇表 ---
    vocab = build_global_vocab(all_texts, lang)

    # --- 4. 分段 ---
    seg_a = segment_text(suspect_text, lang)
    seg_b = segment_text(suspect_author_text, lang)
    seg_controls = [segment_text(c, lang) for c in controls]

    # --- 5. 提取特征 ---
    def build_profile(label: str, segments: List[SegmentInfo]) -> AuthorProfile:
        fvs = [extract_features(seg, vocab) for seg in segments]
        agg = build_aggregate_vector(fvs)
        return AuthorProfile(
            author_label=label,
            segments=segments,
            feature_vectors=fvs,
            aggregate_vector=agg,
        )

    profile_a = build_profile("A", seg_a)
    profile_b = build_profile("B", seg_b)
    control_profiles = [
        build_profile(f"C{i+1}", seg) for i, seg in enumerate(seg_controls)
    ]

    # --- 6. 相似度计算 ---
    sim_b = _compute_similarities(profile_a, profile_b)
    sim_controls = [_compute_similarities(profile_a, cp) for cp in control_profiles]

    # --- 7. 统计检验 ---
    # 配对差：d_i = sim(A_i, B_agg) - mean(sim(A_i, C1_agg), sim(A_i, C2_agg), ...)
    differences = []
    for i, sb in enumerate(sim_b.segment_similarities):
        c_avg = sum(
            sc.segment_similarities[i]
            for sc in sim_controls
            if i < len(sc.segment_similarities)
        )
        n_c = sum(1 for sc in sim_controls if i < len(sc.segment_similarities))
        if n_c > 0:
            differences.append(sb - c_avg / n_c)

    p_w = wilcoxon_signed_rank_test(differences)

    # 置换检验：对每个对照单独做（H0: A↔B 与 A↔Ci 同分布），
    # 取最大 p 值作为最终 p_perm（Bonferroni 风格的保守做法，对抗多重比较假阳性）。
    # 旧版把所有对照的片段相似度堆成一个池，相当于假设所有对照作者同分布，
    # 与"对照代表不同写作风格"的设计相悖。
    p_perms: List[float] = []
    for sc in sim_controls:
        if sc.segment_similarities:
            p_perms.append(
                permutation_test(sim_b.segment_similarities, sc.segment_similarities)
            )
    p_perm = max(p_perms) if p_perms else 1.0

    # Cohen's d（使用样本量加权的合并方差）
    mean_ctrl = sum(
        sc.mean_similarity for sc in sim_controls
    ) / len(sim_controls) if sim_controls else 0.0
    pooled_std_ctrl = math.sqrt(
        sum(sc.std_similarity**2 for sc in sim_controls) / len(sim_controls)
    ) if sim_controls else 0.0
    n_a_segs = len(sim_b.segment_similarities)
    n_ctrl_segs = sum(len(sc.segment_similarities) for sc in sim_controls)
    d_val = cohens_d(
        sim_b.mean_similarity, mean_ctrl, sim_b.std_similarity, pooled_std_ctrl,
        n_a_segs, n_ctrl_segs,
    )

    # --- 8. 判定 ---
    result = FingerprintResult(
        suspect_profile=profile_a,
        suspect_author_profile=profile_b,
        control_profiles=control_profiles,
        similarity_to_b=sim_b,
        similarity_to_controls=sim_controls,
        p_value_wilcoxon=p_w,
        p_value_permutation=p_perm,
        cohens_d=d_val,
    )

    # 判断 B 是否最相似
    is_highest = all(
        sim_b.mean_similarity >= sc.mean_similarity for sc in sim_controls
    )

    if is_highest and p_w < 0.01 and d_val > 0.8:
        result.verdict = "强烈支持"
    elif is_highest and p_w < 0.10 and d_val > 0.3:
        result.verdict = "支持"
    elif is_highest and p_w < 0.10 and d_val > 0.2:
        result.verdict = "弱支持"
    else:
        result.verdict = "不确定"

    return result
