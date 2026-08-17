"""生成 4 篇合成英文测试语料（一次性脚本）。

设计 v2（切片尺度仍可分离）：
- text_the_a / text_the_b：抬高 the / a / and / that / this / with
- text_of_a / text_of_b：抬高 of / in / for / which / by / on
- 每篇 3000 词，由 3 个 1000 词块**独立**生成：每块约 45% 虚词
  （从带组偏差的加权分布抽样）+ 约 55% 内容词（均匀抽自 POOL）。
  组偏差稳定作用于每一个块，而抽样噪声块间独立——与真实语料一致，
  因此整篇与切片（1000/2000 词）两种尺度下组内 Delta 都远小于跨组；
- 组内 a/b 两篇同分布、仅随机种子不同：非 identical，组内 Delta > 0；
- 高频内容词是纯噪声特征，z-score 后为所有文本对贡献相等的噪声地板，
  组间分离完全由偏差虚词提供——信噪结构与真实语料相同。

与 v1 的区别：v1 让填充词频率跨文本严格一致（z-score 阶段零方差剔除），
整篇跑信号极强，但切片破坏该一致性后噪声被 z-score 放大、信号消失。
v2 不依赖这种现实中不存在的退化性质。

实测（n=100 特征词）：
- 整篇：组内 Delta ≈ 1.21，跨组 ≈ 1.52（比值 ≈ 1.26）；
- 1000 词切片（12 片）：组内 ≈ 1.07，跨组 ≈ 1.31（比值 ≈ 1.22）；
- 2000 词切片（8 片）：组内 ≈ 1.10，跨组 ≈ 1.36（比值 ≈ 1.24），
  平均联结层次聚类在三种尺度下均按设计分组。
"""
import random
from pathlib import Path

OUT = Path(__file__).parent

# 内容词池（不含虚词）：均匀高频的纯噪声特征
POOL = (
    "cat dog house tree sun moon river stone bird fish garden road field "
    "walk run sleep eat drink sing read write speak jump sit stand look "
    "happy quiet bright dark quick slow warm cold large small old new "
    "time day night year world life hand eye heart mind door window "
    "friend family child woman man city village forest mountain sea sky "
    "red blue green white black gold silver morning evening winter summer "
    "story song dream light shadow wind rain snow star cloud fire earth"
).split()

# 基础虚词分布（大致 Zipf 形），权重即相对抽样概率
FUNC_BASE = {
    "the": 60, "of": 40, "and": 35, "a": 35, "to": 30, "in": 22,
    "that": 12, "is": 15, "was": 14, "it": 13, "for": 11, "on": 10,
    "with": 10, "as": 9, "at": 8, "by": 7, "be": 7, "this": 6,
    "have": 6, "from": 5, "or": 5, "but": 5, "not": 5, "he": 8,
    "she": 6, "we": 5, "they": 6, "i": 5, "which": 4, "had": 5,
    "are": 4, "were": 3, "an": 6, "his": 4, "her": 3, "their": 3,
}

# 组偏差：对各自偏好的 8 个虚词统一 4 倍加权（模拟译者稳定的虚词使用习惯；
# 实测该强度在整篇与 1000 词切片两种尺度下都能让组间 Delta 稳定盖过噪声地板）
GROUP_BIAS = {
    "the": {w: 4.0 for w in ("the", "a", "and", "that", "this", "with", "he", "not")},
    "of": {w: 4.0 for w in ("of", "in", "for", "which", "by", "on", "as", "but")},
}

N_WORDS = 3000
CHUNK = 1000
FUNC_PER_CHUNK = 450


def to_text(words):
    """每 12 词加一个句号，模拟句子。"""
    sents = []
    for i in range(0, len(words), 12):
        sents.append(" ".join(words[i:i + 12]).capitalize() + ".")
    return " ".join(sents)


def make_chunk(rng, func_words, func_weights):
    """生成一个 1000 词块：450 虚词（加权）+ 550 内容词（均匀）。"""
    words = rng.choices(func_words, weights=func_weights, k=FUNC_PER_CHUNK)
    words += [rng.choice(POOL) for _ in range(CHUNK - FUNC_PER_CHUNK)]
    rng.shuffle(words)
    return words


def main():
    # run_experiment.py 约定：每个一级子目录 = 一个组，组内 *.txt 为样本。
    for group, bias in GROUP_BIAS.items():
        group_dir = OUT / group
        group_dir.mkdir(exist_ok=True)
        func_words = list(FUNC_BASE.keys())
        func_weights = [FUNC_BASE[w] * bias.get(w, 1.0) for w in func_words]
        for suffix in ("a", "b"):
            rng = random.Random(f"v2-{group}-{suffix}")
            words = []
            for _ in range(N_WORDS // CHUNK):
                words += make_chunk(rng, func_words, func_weights)
            assert len(words) == N_WORDS
            text = to_text(words)
            name = f"text_{group}_{suffix}"
            (group_dir / f"{name}.txt").write_text(text, encoding="utf-8")
            top = sorted(bias, key=lambda w: -bias[w])[0]
            ratio = words.count(top) / len(words)
            print(f"{name}.txt: {len(words)} 词, '{top}' 占比 {ratio:.1%}")


if __name__ == "__main__":
    main()
