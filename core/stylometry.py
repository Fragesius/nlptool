"""文体计量模块：Burrows' Delta 译者/作者风格识别。

经典 Burrows' Delta 流程的纯 Python 实现（不依赖 scipy / numpy）：

1. ``tokenize``           英文分词（小写化，仅保留字母单词）
2. ``build_freq_table``   提取合并语料中最高频的 n 个特征词，
                          计算每篇文本在这些词上的相对频率
3. ``zscore``             对每个特征词按全体文本的均值/标准差做 z 标准化
                          （标准差为 0 的词剔除并记录）
4. ``delta_matrix``       两两 Burrows' Delta 距离
                          （所有特征词 z 分数绝对差的均值）
5. ``hierarchical_cluster`` 平均联结（average-linkage）凝聚式层次聚类

约定：
- 频率表以 ``{"features": [...], "frequencies": {文本名: [float, ...]}}``
  表示，频率列表与 features 一一对齐；
- 距离矩阵以 ``{"labels": [...], "matrix": [[float, ...], ...]}`` 表示；
- 聚类树以嵌套 dict 表示：叶子为
  ``{"label": 文本名, "left": None, "right": None, "height": 0.0, "members": [文本名]}``，
  内部节点 ``label`` 为 None，``height`` 为合并距离，``members`` 为全部叶子的文本名。
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List, Optional

__all__ = [
    "TOKEN_PATTERN",
    "tokenize",
    "build_freq_table",
    "zscore",
    "delta_matrix",
    "hierarchical_cluster",
]

# 分词正则：仅保留字母单词（含带撇号的形式如 don't 拆分后取字母段）。
# slice_corpus 与相关测试共用此常量，保证口径一致。
TOKEN_PATTERN = r"[A-Za-z]+"
_TOKEN_RE = re.compile(TOKEN_PATTERN)


def tokenize(text: str) -> List[str]:
    """英文分词：小写化并仅保留字母单词。

    使用正则提取所有连续字母片段，数字、标点、空白均被丢弃。

    :param text: 原始英文文本
    :return: 小写单词列表
    """
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(text)]


def build_freq_table(
    texts: Dict[str, str], n: int = 100, tokenize_fn=None
) -> Dict[str, object]:
    """构建高频特征词相对频率表。

    将全部文本合并后取最高频的 n 个词作为特征词，
    再统计每篇文本中各特征词的相对频率（词频 / 该文本总词数）。

    :param texts: ``{文本名: 原始文本}``
    :param n: 特征词数量（默认 100）
    :param tokenize_fn: 可选分词器覆盖（默认 ``tokenize``）；
                        仅供 v2.3.1 分词器对照实验使用，
                        主管线保持默认不变
    :return: ``{"features": [特征词, ...],
                "frequencies": {文本名: [相对频率, ...]}}``
    """
    tok = tokenize_fn if tokenize_fn is not None else tokenize
    tokens_by_name: Dict[str, List[str]] = {
        name: tok(text) for name, text in texts.items()
    }

    combined: Counter = Counter()
    for tokens in tokens_by_name.values():
        combined.update(tokens)
    # 词频相同时按字典序保证结果确定
    features = [
        w for w, _ in sorted(combined.items(), key=lambda kv: (-kv[1], kv[0]))
    ][:n]

    frequencies: Dict[str, List[float]] = {}
    for name, tokens in tokens_by_name.items():
        counts = Counter(tokens)
        total = len(tokens) or 1  # 空文本防除零
        frequencies[name] = [counts.get(w, 0) / total for w in features]

    return {"features": features, "frequencies": frequencies}


def zscore(freq_table: Dict[str, object]) -> Dict[str, object]:
    """对特征词相对频率做 z 分数标准化。

    对每个特征词，按其在所有文本上的均值与总体标准差
    （除以 N，Burrows 原论文用法）做标准化。
    标准差为 0 的特征词（在所有文本中频率完全一致）被剔除并记录。

    :param freq_table: ``build_freq_table`` 的返回结果
    :return: ``{"features": [保留的特征词, ...],
                "zscores": {文本名: [z 分数, ...]},
                "dropped": [被剔除的特征词, ...]}``
    """
    features: List[str] = freq_table["features"]  # type: ignore[assignment]
    frequencies: Dict[str, List[float]] = freq_table["frequencies"]  # type: ignore[assignment]
    names = list(frequencies.keys())
    n_texts = len(names)

    kept_features: List[str] = []
    dropped: List[str] = []
    kept_cols: List[int] = []
    means: List[float] = []
    stds: List[float] = []

    for j, word in enumerate(features):
        col = [frequencies[name][j] for name in names]
        mean = sum(col) / n_texts
        var = sum((x - mean) ** 2 for x in col) / n_texts
        std = var ** 0.5
        if std == 0.0:
            dropped.append(word)
            continue
        kept_features.append(word)
        kept_cols.append(j)
        means.append(mean)
        stds.append(std)

    zscores: Dict[str, List[float]] = {}
    for name in names:
        zscores[name] = [
            (frequencies[name][j] - means[k]) / stds[k]
            for k, j in enumerate(kept_cols)
        ]

    return {"features": kept_features, "zscores": zscores, "dropped": dropped}


def delta_matrix(
    zscores_data: Dict[str, object],
    progress_callback=None,
) -> Dict[str, object]:
    """计算两两 Burrows' Delta 距离矩阵。

    两篇文本的 Delta 距离定义为：所有特征词 z 分数绝对差的均值。
    矩阵对称，对角线为 0。

    :param zscores_data: ``zscore`` 的返回结果
    :param progress_callback: 可选进度回调
        ``callback(current, total, stage_name)``，每完成一对调用一次
    :return: ``{"labels": [文本名, ...], "matrix": [[距离, ...], ...]}``
    """
    zscores: Dict[str, List[float]] = zscores_data["zscores"]  # type: ignore[assignment]
    labels = list(zscores.keys())
    size = len(labels)
    matrix = [[0.0] * size for _ in range(size)]

    total_pairs = size * (size - 1) // 2
    done = 0
    for i in range(size):
        zi = zscores[labels[i]]
        for j in range(i + 1, size):
            zj = zscores[labels[j]]
            n_feat = len(zi) or 1
            d = sum(abs(a - b) for a, b in zip(zi, zj)) / n_feat
            matrix[i][j] = d
            matrix[j][i] = d
            done += 1
            if progress_callback is not None:
                progress_callback(done, total_pairs, "Delta 矩阵")

    return {"labels": labels, "matrix": matrix}


def hierarchical_cluster(
    matrix: List[List[float]], labels: List[str]
) -> Dict[str, object]:
    """平均联结（average-linkage）凝聚式层次聚类（纯 Python，不用 scipy）。

    从每个文本各自成簇开始，反复合并簇间平均距离最小的一对簇，
    直到只剩一个簇。簇间距离 = 两簇所有成员两两矩阵距离的算术平均。
    并列时按遍历顺序取先出现的一对，保证结果确定。

    :param matrix: 两两距离矩阵（``delta_matrix`` 返回的 matrix）
    :param labels: 与矩阵行列对应的文本名
    :return: 聚类树根节点（嵌套 dict，见模块 docstring）
    """
    index_of = {label: i for i, label in enumerate(labels)}

    def cluster_distance(a: Dict[str, object], b: Dict[str, object]) -> float:
        """两簇间的平均联结距离。"""
        members_a: List[str] = a["members"]  # type: ignore[assignment]
        members_b: List[str] = b["members"]  # type: ignore[assignment]
        total = 0.0
        for la in members_a:
            for lb in members_b:
                total += matrix[index_of[la]][index_of[lb]]
        return total / (len(members_a) * len(members_b))

    clusters: List[Dict[str, object]] = [
        {
            "label": label,
            "left": None,
            "right": None,
            "height": 0.0,
            "members": [label],
        }
        for label in labels
    ]

    while len(clusters) > 1:
        best_pair: Optional[tuple] = None
        best_dist: Optional[float] = None
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                d = cluster_distance(clusters[a], clusters[b])
                if best_dist is None or d < best_dist:
                    best_dist = d
                    best_pair = (a, b)
        assert best_pair is not None
        a, b = best_pair
        merged: Dict[str, object] = {
            "label": None,
            "left": clusters[a],
            "right": clusters[b],
            "height": best_dist,
            "members": list(clusters[a]["members"])  # type: ignore[arg-type]
            + list(clusters[b]["members"]),  # type: ignore[arg-type]
        }
        # 先删索引大的，避免位移
        clusters = [
            c for i, c in enumerate(clusters) if i not in (a, b)
        ]
        clusters.append(merged)

    return clusters[0]
