"""Burrows' Delta stylometry command-line entry point (no UI).

Usage:
    python experiments/run_delta.py --input experiments/sample_corpus \
        --out experiments/output [--top-n 100]

Reads all .txt files in the input folder (text name = filename without
extension), writes delta_matrix.csv and dendrogram.png, and prints key
information to stdout.
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
        print(f"{indent}+ merge distance = {node['height']:.4f}")
        print_merges(node["left"], depth + 1)
        print_merges(node["right"], depth + 1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Burrows' Delta stylometry: author/translator style clustering"
    )
    parser.add_argument("--input", required=True,
                        help="corpus folder (all .txt files inside are read)")
    parser.add_argument("--top-n", type=int, default=100,
                        help="number of feature words (default 100)")
    parser.add_argument("--out", required=True, help="output directory")
    args = parser.parse_args()

    input_dir = Path(args.input)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not input_dir.is_dir():
        print(f"error: input folder not found: {input_dir}", file=sys.stderr)
        sys.exit(1)

    texts = load_corpus(input_dir)
    if len(texts) < 2:
        print(f"error: fewer than 2 .txt files under {input_dir}, "
              f"nothing to compare", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {len(texts)} text(s) (top-{args.top_n} feature words):")
    for name, text in texts.items():
        print(f"  - {name}: {len(tokenize(text))} words")

    freq_table = build_freq_table(texts, n=args.top_n)
    zs = zscore(freq_table)
    print(f"\n{len(freq_table['features'])} feature words, "
          f"{len(zs['dropped'])} dropped for zero standard deviation"
          + (f" ({', '.join(zs['dropped'])})" if zs["dropped"] else ""))

    dm = delta_matrix(zs)
    labels = dm["labels"]
    matrix = dm["matrix"]

    csv_path = out_dir / "delta_matrix.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([""] + labels)
        for label, row in zip(labels, matrix):
            writer.writerow([label] + [f"{d:.6f}" for d in row])
    print(f"\nDelta distance matrix written: {csv_path}")
    for label, row in zip(labels, matrix):
        print("  " + label.ljust(16) + "  ".join(f"{d:.4f}" for d in row))

    tree = hierarchical_cluster(matrix, labels)
    png_path = plot_dendrogram(tree, out_dir / "dendrogram.png")
    print(f"\nHierarchical clustering (average-linkage) merge order:")
    print_merges(tree)
    print(f"\nDendrogram saved: {png_path}")


if __name__ == "__main__":
    main()
