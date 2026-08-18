"""Burrows' Delta 文体计量模块测试。"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.stylometry import (
    tokenize,
    build_freq_table,
    zscore,
    delta_matrix,
    hierarchical_cluster,
)

from tests import _SAMPLE_DIR

SAMPLE_DIR = _SAMPLE_DIR


def test_tokenize():
    """分词：小写化、仅保留字母单词、丢弃数字与标点。"""
    tokens = tokenize("The Cat, sat on 3 mats! Don't stop.")
    assert tokens == ["the", "cat", "sat", "on", "mats", "don", "t", "stop"]
    assert tokenize("12345 !!! ???") == []
    assert tokenize("") == []


def test_build_freq_table():
    """频率表：特征词按合并词频取 top-n，相对频率列与特征词对齐。"""
    texts = {
        "a": "the cat the dog the bird",
        "b": "the dog dog dog fish",
    }
    table = build_freq_table(texts, n=3)
    # 合并词频：the = 3(a)+1(b) = 4，dog = 1(a)+3(b) = 4；同频按字典序 dog 在前
    assert table["features"][:2] == ["dog", "the"]
    # 第三名：cat/bird/fish 各 1 次，按字典序取 bird
    assert table["features"][2] == "bird"
    # a 共 6 词：dog 1/6, the 3/6
    fa = table["frequencies"]["a"]
    assert abs(fa[0] - 1 / 6) < 1e-9
    assert abs(fa[1] - 3 / 6) < 1e-9


def test_zscore_drops_zero_variance():
    """z 标准化：在所有文本中频率一致的词被剔除并记录。"""
    texts = {
        "a": "same same same diff",
        "b": "same same other other",
    }
    table = build_freq_table(texts, n=10)
    zs = zscore(table)
    # "same" 在 a 中 3/4、b 中 2/4，有差异，保留；
    # 构造一个无差异词：两篇各加相同数量的 "flat"
    texts = {
        "a": "flat flat cat dog bird fish",
        "b": "flat flat dog dog bird fish",
    }
    table = build_freq_table(texts, n=10)
    zs = zscore(table)
    # "flat" 两篇均为 2/6，"bird"/"fish" 也相同 → 被剔除
    assert "flat" in zs["dropped"]
    assert "bird" in zs["dropped"]
    assert "dog" in zs["features"]  # 有差异，保留
    # z 分数列表与保留特征词对齐
    assert len(zs["zscores"]["a"]) == len(zs["features"])


def test_delta_matrix_symmetric_and_zero_diagonal():
    """Delta 矩阵：对称、自身距离为 0。"""
    texts = {
        "a": "the cat the dog the bird the fish",
        "b": "of cat of dog of bird of fish",
        "c": "the dog of cat the bird of fish",
    }
    dm = delta_matrix(zscore(build_freq_table(texts, n=10)))
    m = dm["matrix"]
    n = len(m)
    for i in range(n):
        assert m[i][i] == 0.0
        for j in range(n):
            assert abs(m[i][j] - m[j][i]) < 1e-12
            assert m[i][j] >= 0.0


def _top_level_groups(tree):
    """取树根的两个子簇成员集合。"""
    return frozenset(tree["left"]["members"]), frozenset(tree["right"]["members"])


def test_cluster_groups_sample_corpus():
    """冒烟测试：4 篇合成语料按设计分组聚类（the 组 vs of 组）。"""
    texts = {
        p.stem: p.read_text(encoding="utf-8")
        for p in sorted(SAMPLE_DIR.rglob("*.txt"))
    }
    assert len(texts) == 4
    # 组内两篇非 identical：内容与词频都有可控偏移
    assert texts["text_the_a"] != texts["text_the_b"]
    assert texts["text_of_a"] != texts["text_of_b"]
    dm = delta_matrix(zscore(build_freq_table(texts, n=100)))
    labels = dm["labels"]
    # 组内 Delta > 0，但远小于跨组 Delta
    for ga, gb, other in (
        ("text_the_a", "text_the_b", "text_of_a"),
        ("text_of_a", "text_of_b", "text_the_a"),
    ):
        i, j, k = labels.index(ga), labels.index(gb), labels.index(other)
        assert dm["matrix"][i][j] > 0.0
        assert dm["matrix"][i][j] < dm["matrix"][i][k]
    tree = hierarchical_cluster(dm["matrix"], labels)
    g1, g2 = _top_level_groups(tree)
    expected = {
        frozenset({"text_the_a", "text_the_b"}),
        frozenset({"text_of_a", "text_of_b"}),
    }
    assert {g1, g2} == expected


def test_cluster_non_identical_same_style():
    """非 identical 但同组（风格相近）的文本仍聚为一枝。"""
    base = "cat dog house tree sun moon river stone " * 40
    # 同组两篇：共享 base，"the"/"a" 配比不同 → 词频不同、非 identical
    s1 = base + "the " * 60 + "a " * 20
    s2 = base + "the " * 50 + "a " * 30
    # 异组对照：抬高 "of"/"in"
    other = base + "of " * 60 + "in " * 20
    assert s1 != s2
    texts = {"s1": s1, "s2": s2, "other": other}
    dm = delta_matrix(zscore(build_freq_table(texts, n=50)))
    labels = dm["labels"]
    i, j = labels.index("s1"), labels.index("s2")
    assert dm["matrix"][i][j] > 0.0  # 非 identical → Delta 非零
    tree = hierarchical_cluster(dm["matrix"], labels)
    # 3 篇时树根一侧应为 {s1, s2}，另一侧为 {other}
    assert {frozenset(tree["left"]["members"]), frozenset(tree["right"]["members"])} == {
        frozenset({"s1", "s2"}),
        frozenset({"other"}),
    }


def test_cluster_identical_texts_merge_first():
    """两篇完全相同文本的 Delta 为 0，且最先合并。"""
    t = "the quick brown fox jumps over the lazy dog " * 50
    texts = {"x1": t, "x2": t, "y": "of Mice and men " * 100}
    dm = delta_matrix(zscore(build_freq_table(texts, n=20)))
    i, j = dm["labels"].index("x1"), dm["labels"].index("x2")
    assert dm["matrix"][i][j] == 0.0
    tree = hierarchical_cluster(dm["matrix"], dm["labels"])
    # 找到高度最低的内部节点，应是 x1+x2
    def lowest(node):
        if node["label"] is not None:
            return node
        l, r = lowest(node["left"]), lowest(node["right"])
        cand = [n for n in (l, r) if n["label"] is None]
        cand.append(node)
        return min(cand, key=lambda n: n["height"])
    first_merge = lowest(tree)
    assert set(first_merge["members"]) == {"x1", "x2"}
    assert first_merge["height"] == 0.0
