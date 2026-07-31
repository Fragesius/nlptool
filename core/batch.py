"""批量文件分析模块。

为语言学研究者提供对多个文件进行统一基础分析的能力，
输出聚合统计表格，支持导出为 CSV / JSON / DOCX。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional, Callable

from core import analyzer, file_io


@dataclass
class BatchItem:
    """单个文件的批量分析结果。"""

    path: str
    filename: str
    status: str  # "ok" / "error"
    error: str = ""
    lang: str = ""
    char_count: int = 0
    word_count: int = 0
    sentence_count: int = 0
    unique_words: int = 0
    top_words: List[tuple] = field(default_factory=list)


def analyze_files(
    paths: List[str],
    lang: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> List[BatchItem]:
    """批量分析文件列表。

    Args:
        paths: 文件路径列表。
        lang: 语言代码（None 表示自动检测）。
        progress_callback: 进度回调，参数为 (current, total, filename)。

    Returns:
        BatchItem 列表。
    """
    results: List[BatchItem] = []
    total = len(paths)

    for i, path in enumerate(paths, 1):
        filename = os.path.basename(path)
        if progress_callback is not None:
            progress_callback(i, total, filename)

        try:
            text = file_io.read_file(path)
            if not text.strip():
                results.append(
                    BatchItem(
                        path=path,
                        filename=filename,
                        status="error",
                        error="文件为空或无法提取文本",
                    )
                )
                continue

            res = analyzer.analyze_basic(text, lang)
            results.append(
                BatchItem(
                    path=path,
                    filename=filename,
                    status="ok",
                    lang=res.lang_name(),
                    char_count=res.char_count,
                    word_count=res.word_count,
                    sentence_count=res.sentence_count,
                    unique_words=len(res.freq),
                    top_words=res.freq.most_common(5),
                )
            )
        except Exception as e:
            results.append(
                BatchItem(
                    path=path,
                    filename=filename,
                    status="error",
                    error=str(e),
                )
            )

    return results
