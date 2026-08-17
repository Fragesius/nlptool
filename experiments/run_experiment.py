"""Batch grouped experiment entry point for translator style research.

Usage:
    python experiments/run_experiment.py --input <grouped_dir> \
        --out <output_dir> [--top-n 100] [--perm-n 10000] [--lang en]

Input layout convention: each first-level subdirectory of ``--input`` is
one group (e.g. ``translator_A/``, ``translator_B/``); group names are
taken from the directory names and never hard-coded. All ``.txt`` files
inside a group directory are that group's samples (typically chunks
produced by ``slice_corpus.py``).

Pipeline:
    a) Burrows' Delta over all samples (reuses core.stylometry):
       writes ``delta_matrix.csv`` and ``dendrogram.png``
       (reuses viz.dendrogram).
    b) Within-group vs cross-group mean Delta: mean, difference, ratio.
    c) Pairwise linguistic-fingerprint similarity (reuses
       core.linguistic_fingerprint): same-translator pairs vs
       cross-translator pairs, with Wilcoxon signed-rank test,
       permutation test (default 10000 iterations) and Cohen's d.
    d) A Markdown ``report.md`` summarizing all of the above, plus
       ``fingerprint_pairs.csv`` with per-pair similarity details.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Allow running directly from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.stylometry import (  # noqa: E402
    build_freq_table,
    zscore,
    delta_matrix,
    hierarchical_cluster,
)
from core.analyzer import tokenize_many  # noqa: E402
from core.linguistic_fingerprint import (  # noqa: E402
    SegmentInfo,
    build_global_vocab,
    extract_features,
    extract_sentence_stats_many,
    weighted_cosine_similarity,
    wilcoxon_signed_rank_test,
    permutation_test,
    cohens_d,
)
from viz.dendrogram import plot_dendrogram  # noqa: E402


def load_groups(input_dir: Path) -> Dict[str, Dict[str, str]]:
    """Load grouped samples: ``{group_name: {sample_label: text}}``.

    Each first-level subdirectory of ``input_dir`` is a group; every
    ``*.txt`` inside it is a sample labelled ``{group}/{stem}``.

    :param input_dir: experiment input root
    :return: mapping of group name to its samples
    :raises ValueError: fewer than 2 groups, or a group with < 2 samples
    """
    groups: Dict[str, Dict[str, str]] = {}
    for sub in sorted(p for p in input_dir.iterdir() if p.is_dir()):
        samples = {}
        for f in sorted(sub.glob("*.txt"), key=lambda p: p.stem):
            samples[f"{sub.name}/{f.stem}"] = f.read_text(encoding="utf-8")
        if samples:
            groups[sub.name] = samples

    stray = sorted(input_dir.glob("*.txt"))
    if stray:
        print(
            f"warning: {len(stray)} .txt file(s) directly under {input_dir} "
            f"are ignored (samples must live in group subdirectories): "
            + ", ".join(p.name for p in stray),
            file=sys.stderr,
        )

    if len(groups) < 2:
        raise ValueError(
            f"need at least 2 group subdirectories under {input_dir}, "
            f"found {len(groups)}"
        )
    for name, samples in groups.items():
        if len(samples) < 2:
            raise ValueError(
                f"group '{name}' has only {len(samples)} sample(s), "
                f"need at least 2 to compute within-group statistics"
            )
    return groups


def _mean_std(values: List[float]) -> Tuple[float, float]:
    """Return (mean, sample std) of a list (std=0 for n<2).

    Uses the sample standard deviation (divisor n-1), the convention
    expected by ``cohens_d``'s pooled-variance formula.
    """
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, math.sqrt(var)


def _effect_size_note(d: float) -> str:
    """English interpretation label for Cohen's d magnitude."""
    d = abs(d)
    if d < 0.2:
        return "negligible"
    if d < 0.5:
        return "small"
    if d < 0.8:
        return "medium"
    return "large"


def run(
    input_dir: Path,
    out_dir: Path,
    top_n: int = 100,
    perm_n: int = 10000,
    lang: str = "en",
) -> Dict[str, object]:
    """Run the full grouped experiment and write all artifacts.

    :param input_dir: directory containing one subdirectory per group
    :param out_dir: output directory for CSV/PNG/MD artifacts
    :param top_n: number of most-frequent-word features for Delta
    :param perm_n: permutation test iterations
    :param lang: language code for fingerprint features ("en" or "zh")
    :return: dict of key statistics (for testing / programmatic use)
    """
    input_dir = Path(input_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    groups = load_groups(input_dir)
    group_names = list(groups.keys())

    # Flatten samples, remembering each sample's group.
    texts: Dict[str, str] = {}
    group_of: Dict[str, str] = {}
    for gname, samples in groups.items():
        for label, text in samples.items():
            texts[label] = text
            group_of[label] = gname
    labels = list(texts.keys())
    n_samples = len(labels)
    print(f"Loaded {n_samples} samples in {len(groups)} group(s): "
          + ", ".join(f"{g}({len(groups[g])})" for g in group_names))

    # ------------------------------------------------------------------
    # (a) Burrows' Delta matrix + dendrogram
    # ------------------------------------------------------------------
    freq_table = build_freq_table(texts, n=top_n)
    zs = zscore(freq_table)
    dm = delta_matrix(zs)
    matrix: List[List[float]] = dm["matrix"]  # type: ignore[assignment]
    dm_labels: List[str] = dm["labels"]  # type: ignore[assignment]

    csv_path = out_dir / "delta_matrix.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([""] + dm_labels)
        for label, row in zip(dm_labels, matrix):
            writer.writerow([label] + [f"{d:.6f}" for d in row])
    print(f"Delta matrix written: {csv_path}")

    tree = hierarchical_cluster(matrix, dm_labels)
    png_path = plot_dendrogram(
        tree, out_dir / "dendrogram.png",
        title="Burrows' Delta Clustering: " + " vs ".join(group_names),
    )
    print(f"Dendrogram saved: {png_path}")

    # ------------------------------------------------------------------
    # (b) Within-group vs cross-group mean Delta
    # ------------------------------------------------------------------
    idx_of = {label: i for i, label in enumerate(dm_labels)}
    within_deltas: List[float] = []
    cross_deltas: List[float] = []
    for i, la in enumerate(dm_labels):
        for j in range(i + 1, len(dm_labels)):
            lb = dm_labels[j]
            if group_of[la] == group_of[lb]:
                within_deltas.append(matrix[i][j])
            else:
                cross_deltas.append(matrix[i][j])

    within_mean, within_std = _mean_std(within_deltas)
    cross_mean, cross_std = _mean_std(cross_deltas)
    delta_diff = cross_mean - within_mean
    delta_ratio = cross_mean / within_mean if within_mean > 0 else math.inf
    print(f"Within-group Delta: {within_mean:.4f} (n={len(within_deltas)}); "
          f"cross-group: {cross_mean:.4f} (n={len(cross_deltas)}); "
          f"diff={delta_diff:.4f}, ratio={delta_ratio:.2f}")

    # ------------------------------------------------------------------
    # (c) Pairwise linguistic fingerprint similarity
    # ------------------------------------------------------------------
    # 性能重构（v2.0.0）：每个样本只分词一次、只提取一次特征。
    # - tokenize_many：英文走 spaCy nlp.pipe 批处理，结果与逐条分词一致；
    # - extract_sentence_stats_many：全部句子一次性批量分词；
    # - 预分词结果同时供 build_global_vocab 与 extract_features 复用，
    #   避免旧路径中"建词汇表一遍、提特征又一遍"的重复分词。
    text_list = [texts[label] for label in labels]
    token_list = tokenize_many(text_list, lang)
    sent_stats_list = extract_sentence_stats_many(text_list, lang)

    vocab = build_global_vocab(text_list, lang, tokenized=token_list)
    fvs = {}
    for label, text, toks, sst in zip(labels, text_list, token_list,
                                      sent_stats_list):
        seg = SegmentInfo(
            text=text, segment_index=0, char_count=len(text), lang=lang
        )
        fvs[label] = extract_features(seg, vocab, tokens=toks, sent_stats=sst)

    # Similarity of every unordered pair, grouped by same/cross translator.
    sim_pair: Dict[Tuple[str, str], float] = {}
    same_sims: List[float] = []
    cross_sims: List[float] = []
    for i, la in enumerate(labels):
        for j in range(i + 1, len(labels)):
            lb = labels[j]
            sim = weighted_cosine_similarity(fvs[la], fvs[lb])
            sim_pair[(la, lb)] = sim
            if group_of[la] == group_of[lb]:
                same_sims.append(sim)
            else:
                cross_sims.append(sim)

    pairs_path = out_dir / "fingerprint_pairs.csv"
    with pairs_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["sample_a", "sample_b", "pair_type", "similarity"])
        for (la, lb), sim in sim_pair.items():
            ptype = "same" if group_of[la] == group_of[lb] else "cross"
            writer.writerow([la, lb, ptype, f"{sim:.6f}"])
    print(f"Pairwise fingerprint similarities written: {pairs_path}")

    same_mean, same_std = _mean_std(same_sims)
    cross_mean_sim, cross_std_sim = _mean_std(cross_sims)

    # Wilcoxon signed-rank test on per-sample paired differences:
    # d_i = mean sim of sample i to same-group others
    #       - mean sim of sample i to cross-group samples.
    def _pair_sim(a: str, b: str) -> float:
        return sim_pair[(a, b)] if (a, b) in sim_pair else sim_pair[(b, a)]

    differences: List[float] = []
    for la in labels:
        same_to = [_pair_sim(la, lb) for lb in labels
                   if lb != la and group_of[lb] == group_of[la]]
        cross_to = [_pair_sim(la, lb) for lb in labels
                    if group_of[lb] != group_of[la]]
        differences.append(
            sum(same_to) / len(same_to) - sum(cross_to) / len(cross_to)
        )
    p_wilcoxon = wilcoxon_signed_rank_test(differences)
    p_perm = permutation_test(same_sims, cross_sims, n_iter=perm_n)
    d_val = cohens_d(
        same_mean, cross_mean_sim, same_std, cross_std_sim,
        len(same_sims), len(cross_sims),
    )
    print(f"Fingerprint: same-translator sim {same_mean:.4f} "
          f"(n={len(same_sims)}), cross-translator {cross_mean_sim:.4f} "
          f"(n={len(cross_sims)}); Wilcoxon p={p_wilcoxon:.4f}, "
          f"permutation p={p_perm:.4f}, Cohen's d={d_val:.3f}")

    # ------------------------------------------------------------------
    # (d) Markdown report
    # ------------------------------------------------------------------
    # Both tests must pass: taking the max p-value is the conservative
    # choice (mirrors the Bonferroni-style max in core.linguistic_fingerprint).
    significant = (
        max(p_wilcoxon, p_perm) < 0.05 and same_mean > cross_mean_sim
    )
    if same_mean <= cross_mean_sim:
        conclusion = (
            f"同译者对相似度（{same_mean:.4f}）并未高于跨译者对"
            f"（{cross_mean_sim:.4f}），未检测到译者风格信号盖过原文信号的证据。"
        )
    elif significant:
        conclusion = (
            f"同译者对相似度显著高于跨译者对"
            f"（Wilcoxon p={p_wilcoxon:.4f}，置换检验 p={p_perm:.4f}，"
            f"Cohen's d={d_val:.3f}，{_effect_size_note(d_val)}效应），"
            f"译者风格信号在本语料上可识别。"
        )
    else:
        conclusion = (
            f"同译者对相似度（{same_mean:.4f}）高于跨译者对"
            f"（{cross_mean_sim:.4f}），但差异未达统计显著"
            f"（Wilcoxon p={p_wilcoxon:.4f}，置换检验 p={p_perm:.4f}，"
            f"Cohen's d={d_val:.3f}）。"
        )

    ratio_str = f"{delta_ratio:.2f}" if math.isfinite(delta_ratio) else "inf (within=0)"
    delta_warning: List[str] = []
    if not (math.isfinite(delta_ratio) and delta_ratio > 1.1):
        delta_warning = [
            "",
            "> ⚠ **Sanity check**: cross/within Delta ratio is "
            f"{ratio_str} (≤ 1.1) —— Burrows' Delta 未检测到组间分离。"
            "可能原因：切片过短、语料过于同质、或高频特征被内容噪声主导。"
            "请勿将阴性 Delta 直接解读为「无译者风格」，"
            "结论应结合下方指纹相似度与统计检验综合判断。",
        ]
    report_lines = [
        "# Translator Style Experiment Report",
        "",
        "## Samples",
        "",
        f"- Groups: {len(groups)} ("
        + ", ".join(f"`{g}`: {len(groups[g])} samples" for g in group_names)
        + ")",
        f"- Total samples: {n_samples}",
        f"- Delta features: top-{top_n} most frequent words "
        f"({len(zs['dropped'])} zero-variance feature(s) dropped)",
        "",
        "## Burrows' Delta",
        "",
        "| Statistic | Within-group | Cross-group |",
        "| --- | --- | --- |",
        f"| Mean | {within_mean:.4f} | {cross_mean:.4f} |",
        f"| Std | {within_std:.4f} | {cross_std:.4f} |",
        f"| Pairs | {len(within_deltas)} | {len(cross_deltas)} |",
        "",
        f"- Difference (cross - within): **{delta_diff:.4f}**",
        f"- Ratio (cross / within): **{ratio_str}**",
    ] + delta_warning + [
        "",
        "![Dendrogram](dendrogram.png)",
        "",
        "## Linguistic Fingerprint Similarity",
        "",
        "| Statistic | Same-translator pairs | Cross-translator pairs |",
        "| --- | --- | --- |",
        f"| Mean | {same_mean:.4f} | {cross_mean_sim:.4f} |",
        f"| Std | {same_std:.4f} | {cross_std_sim:.4f} |",
        f"| Pairs | {len(same_sims)} | {len(cross_sims)} |",
        "",
        f"- Wilcoxon signed-rank test: p = **{p_wilcoxon:.4f}**",
        f"- Permutation test ({perm_n} iterations): p = **{p_perm:.4f}**",
        f"- Cohen's d = **{d_val:.3f}** ({_effect_size_note(d_val)})",
        "",
        "## 结论",
        "",
        conclusion,
        "",
    ]
    report_path = out_dir / "report.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Report written: {report_path}")

    return {
        "groups": {g: len(s) for g, s in groups.items()},
        "n_samples": n_samples,
        "within_delta_mean": within_mean,
        "cross_delta_mean": cross_mean,
        "delta_diff": delta_diff,
        "delta_ratio": delta_ratio,
        "same_sim_mean": same_mean,
        "cross_sim_mean": cross_mean_sim,
        "p_wilcoxon": p_wilcoxon,
        "p_permutation": p_perm,
        "cohens_d": d_val,
        "significant": significant,
        # report.md 结论段的中文模板文字，供 GUI 等调用方直接展示
        "conclusion": conclusion,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Grouped translator-style experiment: "
                    "Burrows' Delta + linguistic fingerprint"
    )
    parser.add_argument("--input", required=True,
                        help="input root; each subdirectory is one group")
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument("--top-n", type=int, default=100,
                        help="number of Delta feature words (default 100)")
    parser.add_argument("--perm-n", type=int, default=10000,
                        help="permutation test iterations (default 10000)")
    parser.add_argument("--lang", default="en", choices=["en", "zh"],
                        help="sample language for fingerprint features "
                             "(default en)")
    args = parser.parse_args()

    input_dir = Path(args.input)
    if not input_dir.is_dir():
        print(f"error: input directory not found: {input_dir}",
              file=sys.stderr)
        sys.exit(1)

    try:
        run(input_dir, Path(args.out), top_n=args.top_n,
            perm_n=args.perm_n, lang=args.lang)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
