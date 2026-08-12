"""Burrows' Delta 文体计量命令行入口（不走 UI）。

用法：
    python experiments/run_delta.py --input experiments/sample_corpus \
        --out experiments/output [--top-n 100]

读取输入文件夹中全部 .txt 文件（文本名 = 文件名去扩展名），
输出 delta_matrix.csv 与 dendrogram.png，关键信息打印到 stdout。
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# 允许从仓库根目录直接运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.stylometry import (  # noqa: E402
    tokenize,
    build_freq_table,
    zscore,
    delta_matrix,
    hierarchical_cluster,
)
from viz.dendrogram import plot_dendrogram  # noqa: E402


def load_corpus(input_dir: Path) -> dict:
    """读取文件夹中全部 .txt，返回 {文件名去扩展名: 文本}（按名字排序）。"""
    texts = {}
    for path in sorted(input_dir.glob("*.txt"), key=lambda p: p.stem):
        texts[path.stem] = path.read_text(encoding="utf-8")
    return texts


def print_merges(node: dict, depth: int = 0) -> None:
    """以缩进树形式打印合并过程。"""
    indent = "  " * depth
    if node["label"] is not None:
        print(f"{indent}· {node['label']}")
    else:
        print(f"{indent}+ 合并距离 = {node['height']:.4f}")
        print_merges(node["left"], depth + 1)
        print_merges(node["right"], depth + 1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Burrows' Delta 文体计量：译者/作者风格聚类"
    )
    parser.add_argument("--input", required=True, help="语料文件夹（读取其中全部 .txt）")
    parser.add_argument("--top-n", type=int, default=100, help="特征词数量（默认 100）")
    parser.add_argument("--out", required=True, help="输出目录")
    args = parser.parse_args()

    input_dir = Path(args.input)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.is_dir():
        print(f"错误：输入文件夹不存在：{input_dir}", file=sys.stderr)
        sys.exit(1)

    texts = load_corpus(input_dir)
    if len(texts) < 2:
        print(f"错误：{input_dir} 中 .txt 少于 2 篇，无法比较", file=sys.stderr)
        sys.exit(1)

    print(f"已加载 {len(texts)} 篇文本（特征词 top-{args.top_n}）：")
    for name, text in texts.items():
        print(f"  - {name}: {len(tokenize(text))} 词")

    freq_table = build_freq_table(texts, n=args.top_n)
    zs = zscore(freq_table)
    print(f"\n特征词 {len(freq_table['features'])} 个，"
          f"其中标准差为 0 被剔除 {len(zs['dropped'])} 个"
          + (f"（{', '.join(zs['dropped'])}）" if zs["dropped"] else ""))

    dm = delta_matrix(zs)
    labels = dm["labels"]
    matrix = dm["matrix"]

    csv_path = out_dir / "delta_matrix.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([""] + labels)
        for label, row in zip(labels, matrix):
            writer.writerow([label] + [f"{d:.6f}" for d in row])
    print(f"\nDelta 距离矩阵已写入：{csv_path}")
    for label, row in zip(labels, matrix):
        print("  " + label.ljust(16) + "  ".join(f"{d:.4f}" for d in row))

    tree = hierarchical_cluster(matrix, labels)
    png_path = plot_dendrogram(tree, out_dir / "dendrogram.png")
    print(f"\n层次聚类（average-linkage）合并过程：")
    print_merges(tree)
    print(f"\n树状图已保存：{png_path}")


if __name__ == "__main__":
    main()
