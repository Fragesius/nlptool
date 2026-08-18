"""性能回归测试（v2.0.0 阶段一）。

核心断言：分组实验中每个样本的特征提取恰好一次（O(n)），
不随配对数 O(n²) 增长。用 experiments/sample_corpus 的词料构造
30 个样本（2 组 × 15），通过计数器包装 extract_features 验证。

Compatible with ``python run_tests.py`` (plain functions, no pytest).
"""

from __future__ import annotations

import random
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.stylometry import TOKEN_PATTERN  # noqa: E402
from tests import _SAMPLE_DIR, has_matplotlib  # noqa: E402

_WORD_RE = re.compile(TOKEN_PATTERN)

N_GROUPS = 2
SAMPLES_PER_GROUP = 15  # 共 30 个样本
WORDS_PER_SAMPLE = 400


def _group_words(group_dir: str) -> list:
    """sample_corpus 某组全部文本的词料（小写）。"""
    words = []
    for f in sorted((_SAMPLE_DIR / group_dir).glob("*.txt")):
        words.extend(
            m.group(0).lower()
            for m in _WORD_RE.finditer(f.read_text(encoding="utf-8"))
        )
    return words


def _build_30_sample_corpus(root: Path) -> Path:
    """用 sample_corpus 词料确定性构造 translator_A/B 各 15 个样本。"""
    rng = random.Random(20260817)
    pools = {
        "translator_A": _group_words("the"),
        "translator_B": _group_words("of"),
    }
    inp = root / "input"
    for group, pool in pools.items():
        gdir = inp / group
        gdir.mkdir(parents=True)
        for i in range(1, SAMPLES_PER_GROUP + 1):
            text = " ".join(rng.choice(pool) for _ in range(WORDS_PER_SAMPLE))
            (gdir / f"sample{i:03d}.txt").write_text(text, encoding="utf-8")
    return inp


def test_feature_extraction_count_equals_sample_count():
    """30 个样本的分组实验中，extract_features 恰好被调用 30 次。"""
    if not has_matplotlib():
        print("    (skipped: matplotlib not installed)")
        return

    import experiments.run_experiment as rexp
    import experiments.weight_sensitivity as ws

    n_samples = N_GROUPS * SAMPLES_PER_GROUP
    calls = []
    # run() 的特征提取走 weight_sensitivity.extract_corpus_features，
    # 其内部调用该模块全局的 extract_features，包装它即可计数。
    original = ws.extract_features

    def counting_extract_features(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inp = _build_30_sample_corpus(root)
        out = root / "out"

        ws.extract_features = counting_extract_features
        try:
            stats = rexp.run(inp, out, perm_n=200)
        finally:
            ws.extract_features = original

        assert stats["n_samples"] == n_samples
        assert len(calls) == n_samples, (
            f"extract_features 调用 {len(calls)} 次，"
            f"应等于样本数 {n_samples}（O(n) 提取）"
        )


def test_batch_paths_match_sequential_results():
    """批量分词 / 批量句长统计与逐条调用结果完全一致（零变化底线）。"""
    from core.analyzer import tokenize, tokenize_many
    from core.linguistic_fingerprint import (
        extract_sentence_stats,
        extract_sentence_stats_many,
    )

    texts = [
        "The quick brown fox jumps over the lazy dog. And again, quickly!",
        "Of mice and men, for whom the bell tolls; in time, by design.",
        "Short.",
    ]
    for lang in ("en",):
        batch = tokenize_many(texts, lang)
        sequential = [tokenize(t, lang) for t in texts]
        for bt, st in zip(batch, sequential):
            assert [(t.text, t.pos, t.lemma, t.is_stop) for t in bt] == [
                (t.text, t.pos, t.lemma, t.is_stop) for t in st
            ], "tokenize_many 与逐条 tokenize 结果不一致"

        stats_batch = extract_sentence_stats_many(texts, lang)
        stats_seq = [extract_sentence_stats(t, lang) for t in texts]
        assert stats_batch == stats_seq, (
            f"句长统计批量/逐条不一致: {stats_batch} vs {stats_seq}"
        )


def test_extract_features_accepts_precomputed_inputs():
    """extract_features 传入预分词/预算句长统计时，结果与内部计算一致。"""
    from core.analyzer import tokenize
    from core.linguistic_fingerprint import (
        SegmentInfo,
        build_global_vocab,
        extract_features,
        extract_sentence_stats,
        weighted_cosine_similarity,
    )

    text_a = "The cat sat on the mat. The dog ran fast, and the cat ran too."
    text_b = "Of all the things, in time and for good measure, by design."
    texts = [text_a, text_b]
    lang = "en"

    vocab_plain = build_global_vocab(texts, lang)
    vocab_pre = build_global_vocab(
        texts, lang, tokenized=[tokenize(t, lang) for t in texts]
    )
    assert vocab_plain == vocab_pre, "build_global_vocab 预分词路径结果不一致"

    seg = SegmentInfo(text=text_a, segment_index=0, char_count=len(text_a), lang=lang)
    fv_plain = extract_features(seg, vocab_plain)
    fv_pre = extract_features(
        seg,
        vocab_pre,
        tokens=tokenize(text_a, lang),
        sent_stats=extract_sentence_stats(text_a, lang),
    )
    assert fv_plain == fv_pre, "extract_features 预计算路径结果不一致"

    seg_b = SegmentInfo(text=text_b, segment_index=0, char_count=len(text_b), lang=lang)
    fv_b = extract_features(seg_b, vocab_plain)
    sim = weighted_cosine_similarity(fv_plain, fv_b)
    # 范数缓存路径再次计算，结果必须逐位一致
    sim2 = weighted_cosine_similarity(fv_plain, fv_b)
    assert sim == sim2 and 0.0 <= sim <= 1.0
