"""生成 4 篇合成英文测试语料（一次性脚本）。

设计（供 Burrows' Delta 冒烟测试验证聚类正确性）：
- text_the_a / text_the_b：显著抬高 "the" 的使用频率（约 15%）
- text_of_a / text_of_b：显著抬高 "of" 的使用频率（约 15%）
- 四篇共享完全相同的填充词多重集，因此组间差异只来自目标词；
  组内两篇为同一词表的不同排列（词频完全一致，Delta 为 0，
  模拟"同一风格写就的两段不同文字"）。

注意：Burrows' Delta 先做 z 分数标准化，任何纯随机噪声特征都会被
放大到单位方差并淹没目标词信号，故合成语料必须让填充词频率
跨文本严格一致，不能用随机扰动模拟"真实感"。
"""
import random
from pathlib import Path

OUT = Path(__file__).parent

# 填充词池（刻意不含 the/of，便于精确控制二者频率）
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
N_TARGET = 450  # 目标词约占 15%


def to_text(words):
    """每 12 词加一个句号，模拟句子。"""
    sents = []
    for i in range(0, len(words), 12):
        sents.append(" ".join(words[i:i + 12]).capitalize() + ".")
    return " ".join(sents)


def main():
    rng = random.Random(7)
    fillers = [rng.choice(POOL) for _ in range(N_WORDS - N_TARGET)]

    for group, target in (("the", "the"), ("of", "of")):
        # 文本 A：目标词均匀穿插在填充词中
        step = (N_WORDS - N_TARGET) / N_TARGET
        words_a = []
        fi = 0
        for k in range(N_TARGET):
            words_a.append(target)
            take = round((k + 1) * step) - round(k * step)
            words_a.extend(fillers[fi:fi + take])
            fi += take
        words_a.extend(fillers[fi:])
        # 文本 B：同一词表打乱排列（词频与 A 完全一致）
        words_b = words_a[:]
        random.Random(11).shuffle(words_b)

        for suffix, words in (("a", words_a), ("b", words_b)):
            text = to_text(words)
            name = f"text_{group}_{suffix}"
            (OUT / f"{name}.txt").write_text(text, encoding="utf-8")
            n = len(text.split())
            c = sum(1 for w in words if w == target)
            print(f"{name}.txt: {n} 词, '{target}' 出现 {c} 次 ({c / n:.1%})")


if __name__ == "__main__":
    main()
