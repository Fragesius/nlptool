"""生成 4 篇合成英文测试语料（一次性脚本）。

设计（供 Burrows' Delta 冒烟测试验证聚类正确性）：
- text_the_a / text_the_b：显著抬高定冠词 "the"（配套虚词 "a"）
- text_of_a / text_of_b：显著抬高介词 "of"（配套虚词 "in"）
- 四篇共享完全相同的填充词多重集（2550 词），总长均为 3000 词，
  因此填充词在 z-score 阶段因零方差被全部剔除，不稀释虚词信号；
- 组内两篇**非 identical**：通过「目标虚词 ↔ 配套虚词」配比微调
  制造可控的频率偏移（如 the 300+a 150 vs the 270+a 180），
  并各自独立 shuffle，内容与词频都不同，但风格相近。
  实测组内 Delta ≈ 0.14，跨组 Delta ≈ 1.95（约 14 倍差距），
  平均联结层次聚类仍按设计把同组两篇先聚为一枝。

注意：Burrows' Delta 先做 z 分数标准化，任何纯随机噪声特征都会被
放大到单位方差并淹没目标词信号，故合成语料必须让填充词频率
跨文本严格一致；组内差异只允许来自成对虚词的配比此消彼长
（总词数保持一致），不能用随机扰动模拟"真实感"。
"""
import random
from pathlib import Path

OUT = Path(__file__).parent

# 填充词池（刻意不含任何虚词，便于精确控制目标虚词频率）
POOL = (
    "cat dog house tree sun moon river stone bird fish garden road field "
    "walk run sleep eat drink sing read write speak jump sit stand look "
    "happy quiet bright dark quick slow warm cold large small old new "
    "time day night year world life hand eye heart mind door window "
    "friend family child woman man city village forest mountain sea sky "
    "red blue green white black gold silver morning evening winter summer "
    "story song dream light shadow wind rain snow star cloud fire earth"
).split()

N_WORDS = 3000
N_FILLERS = 2550

# 每组：(目标虚词, a 篇目标词数, b 篇目标词数, 配套虚词, a 篇配套词数, b 篇配套词数)
# a/b 两篇虚词总量相等（总词数一致），但配比不同 → 组内频率非 identical
GROUPS = {
    "the": ("the", 300, 270, "a", 150, 180),
    "of": ("of", 300, 270, "in", 150, 180),
}


def to_text(words):
    """每 12 词加一个句号，模拟句子。"""
    sents = []
    for i in range(0, len(words), 12):
        sents.append(" ".join(words[i:i + 12]).capitalize() + ".")
    return " ".join(sents)


def main():
    rng = random.Random(7)
    fillers = [rng.choice(POOL) for _ in range(N_FILLERS)]

    for group, (w1, n1a, n1b, w2, n2a, n2b) in GROUPS.items():
        for suffix, c1, c2 in (("a", n1a, n2a), ("b", n1b, n2b)):
            words = fillers + [w1] * c1 + [w2] * c2
            assert len(words) == N_WORDS
            # 每篇独立 shuffle：词序与词频在组内均不同
            random.Random(f"{group}-{suffix}").shuffle(words)
            text = to_text(words)
            name = f"text_{group}_{suffix}"
            (OUT / f"{name}.txt").write_text(text, encoding="utf-8")
            n = len(text.split())
            print(f"{name}.txt: {n} 词, "
                  f"'{w1}' x{c1} ({c1 / n:.1%}), '{w2}' x{c2} ({c2 / n:.1%})")


if __name__ == "__main__":
    main()
