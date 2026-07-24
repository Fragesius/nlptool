"""对比分析与可读性模块。

- 英文可读性：Flesch Reading Ease / Flesch-Kincaid Grade
- 中文可读性：基于句长与词频的简化公式
- 中英双语对齐：基于句子序号与长度的启发式对齐辅助
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .analyzer import split_sentences, tokenize, detect_language


# --------------------------------------------------------------------------- #
# 英文可读性
# --------------------------------------------------------------------------- #

_VOWEL_RE = re.compile(r"[aeiouy]+", re.I)


def _syllable_count(word: str) -> int:
    word = word.lower().strip()
    if not word:
        return 0
    # 末尾静音 e
    if word.endswith("e") and len(word) > 2:
        word = word[:-1]
    groups = _VOWEL_RE.findall(word)
    return max(len(groups), 1)


@dataclass
class EnReadability:
    flesch_ease: float
    flesch_kincaid: float
    avg_sentence_length: float
    avg_syllables_per_word: float
    grade_level: str

    def summary(self) -> str:
        return (
            f"Flesch 易读度: {self.flesch_ease:.2f}（{self.grade_level}）\n"
            f"Flesch-Kincaid 年级: {self.flesch_kincaid:.2f}\n"
            f"平均句长: {self.avg_sentence_length:.2f} 词\n"
            f"平均音节/词: {self.avg_syllables_per_word:.2f}"
        )


def _ease_label(score: float) -> str:
    if score >= 90:
        return "非常容易（5 年级）"
    if score >= 70:
        return "容易（6-7 年级）"
    if score >= 60:
        return "标准（8-9 年级）"
    if score >= 50:
        return "较难（10-12 年级）"
    if score >= 30:
        return "困难（大学生）"
    return "非常困难（研究生）"


def english_readability(text: str) -> EnReadability:
    sentences = split_sentences(text)
    words = re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)*", text)
    n_words = max(len(words), 1)
    n_sents = max(len(sentences), 1)
    syl = sum(_syllable_count(w) for w in words)
    asl = len(words) / n_sents
    asw = syl / n_words
    ease = 206.835 - 1.015 * asl - 84.6 * asw
    fk = 0.39 * asl + 11.8 * asw - 15.59
    return EnReadability(
        flesch_ease=round(ease, 2),
        flesch_kincaid=round(fk, 2),
        avg_sentence_length=round(asl, 2),
        avg_syllables_per_word=round(asw, 2),
        grade_level=_ease_label(ease),
    )


# --------------------------------------------------------------------------- #
# 中文可读性（简化版）
# --------------------------------------------------------------------------- #


@dataclass
class ZhReadability:
    avg_sentence_length: float  # 平均每句字数
    avg_word_length: float  # 平均每词字数
    word_richness: float  # 词汇丰富度（型/比）
    score: float  # 0-100，越高越易读
    level: str

    def summary(self) -> str:
        return (
            f"平均句长: {self.avg_sentence_length:.2f} 字\n"
            f"平均词长: {self.avg_word_length:.2f} 字\n"
            f"词汇丰富度: {self.word_richness:.3f}\n"
            f"可读性评分: {self.score:.1f}/100（{self.level}）"
        )


def chinese_readability(text: str) -> ZhReadability:
    sentences = split_sentences(text)
    n_sents = max(len(sentences), 1)
    chars = [c for c in text if c.strip()]
    asl = len(chars) / n_sents

    tokens = [t.text for t in tokenize(text, "zh") if t.text.strip()]
    n_tokens = max(len(tokens), 1)
    awl = len(chars) / n_tokens
    richness = len(set(tokens)) / n_tokens

    # 简化评分：句长越短、词汇越丰富越易读
    score = 100 - (asl - 15) * 2 - (1 - richness) * 30
    score = max(0, min(100, score))
    if score >= 80:
        level = "易读"
    elif score >= 60:
        level = "中等"
    elif score >= 40:
        level = "较难"
    else:
        level = "困难"
    return ZhReadability(
        avg_sentence_length=round(asl, 2),
        avg_word_length=round(round(awl, 2), 2),
        word_richness=round(richness, 3),
        score=round(score, 1),
        level=level,
    )


# --------------------------------------------------------------------------- #
# 中英对齐（启发式）
# --------------------------------------------------------------------------- #


@dataclass
class Alignment:
    pairs: List[Tuple[str, str]] = field(default_factory=list)
    unmatched_zh: List[str] = field(default_factory=list)
    unmatched_en: List[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"对齐句对: {len(self.pairs)}\n"
            f"未匹配中文: {len(self.unmatched_zh)}\n"
            f"未匹配英文: {len(self.unmatched_en)}"
        )


def align_zh_en(zh_text: str, en_text: str) -> Alignment:
    """按句子序号启发式对齐中英文本。

    仅作长度比例过滤的序号对齐，适合结构对应的平行语料。
    """
    zh_sents = split_sentences(zh_text)
    en_sents = split_sentences(en_text)
    pairs: List[Tuple[str, str]] = []
    i = 0
    while i < min(len(zh_sents), len(en_sents)):
        zh, en = zh_sents[i], en_sents[i]
        zh_len = len([c for c in zh if c.strip()])
        en_len = max(len(en.split()), 1)
        # 中文字数通常是英文词数的 1.0~2.5 倍
        ratio = zh_len / en_len if en_len else 0
        if 0.3 < ratio < 4.0:
            pairs.append((zh, en))
        i += 1
    return Alignment(
        pairs=pairs,
        unmatched_zh=zh_sents[len(pairs):],
        unmatched_en=en_sents[len(pairs):],
    )


def readability_for(text: str, lang: Optional[str] = None):
    """根据语言返回对应可读性结果。"""
    lang = lang or detect_language(text)
    if lang == "zh":
        return chinese_readability(text)
    return english_readability(text)
