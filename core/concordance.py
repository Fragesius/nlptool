"""共现 / KWIC（Key Word In Context）分析模块。

为语言学研究者提供经典的"关键词居中"上下文查看功能。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from core.analyzer import Token, tokenize, detect_language


@dataclass
class KwicLine:
    """一条 KWIC 结果。"""

    left: str       # 左侧上下文
    keyword: str    # 检索词（原始形式）
    right: str      # 右侧上下文
    position: int   # 在文本中的词元位置
    sentence: str = ""  # 所属句子（可选）


def kwic(
    text: str,
    keyword: str,
    lang: Optional[str] = None,
    window: int = 6,
    case_sensitive: bool = False,
    regex: bool = False,
) -> List[KwicLine]:
    """生成关键词上下文（KWIC）列表。

    Args:
        text: 输入文本。
        keyword: 检索词。
        lang: 语言代码，None 则自动检测。
        window: 左右上下文词元数。
        case_sensitive: 是否区分大小写（英文）。
        regex: 是否使用正则匹配。

    Returns:
        KwicLine 列表。
    """
    if not text.strip() or not keyword.strip():
        return []

    lang = lang or detect_language(text)
    tokens = tokenize(text, lang)

    flags = 0 if case_sensitive else re.IGNORECASE
    if regex:
        pattern = re.compile(keyword, flags)
    else:
        pattern = re.compile(re.escape(keyword), flags)

    results: List[KwicLine] = []
    for i, tok in enumerate(tokens):
        text_to_match = tok.text
        if not pattern.search(text_to_match):
            # 也尝试匹配 lemma（英文词形还原）
            if lang == "en" and tok.lemma and pattern.search(tok.lemma):
                text_to_match = tok.lemma
            else:
                continue

        left_tokens = tokens[max(0, i - window):i]
        right_tokens = tokens[i + 1:min(len(tokens), i + 1 + window)]

        left = "".join(t.text for t in left_tokens)
        right = "".join(t.text for t in right_tokens)

        results.append(KwicLine(
            left=left,
            keyword=tok.text,
            right=right,
            position=i,
        ))

    return results


def kwic_summary(lines: List[KwicLine]) -> str:
    """将 KWIC 结果格式化为可阅读文本。"""
    if not lines:
        return "未找到匹配结果。"
    out = [f"共找到 {len(lines)} 条匹配：", ""]
    max_left = max(len(line.left) for line in lines)
    for line in lines:
        left_padded = line.left.rjust(max_left)
        out.append(f"{left_padded}  [{line.keyword}]  {line.right}")
    return "\n".join(out)
