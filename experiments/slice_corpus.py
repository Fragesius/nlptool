"""Corpus slicing preprocessor for stylometry experiments.

Usage:
    python experiments/slice_corpus.py --input <corpus_dir> \
        --out <output_dir> [--chunk-size 2000]

Splits every ``.txt`` file under the input directory (recursively) into
chunks of approximately ``--chunk-size`` English words. A trailing chunk
shorter than 0.5 x chunk-size is discarded; one of at least half the
target size is kept as a chunk of its own.

Output files are named ``{original_stem}__chunk{NNN}.txt`` (1-based,
zero-padded) and mirror the input directory structure under ``--out``.

Tokenization follows ``core.stylometry.tokenize`` (regex ``[A-Za-z]+``),
but chunks are cut from the *original* text so punctuation and whitespace
are preserved for downstream feature extraction.

With ``--clean``, the output directory is emptied (all files and
subdirectories under it deleted) before slicing begins. Refuses to clean
dangerous locations (filesystem root, user home, etc.).
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import List

# Allow running directly from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.stylometry import TOKEN_PATTERN  # noqa: E402


def clean_output_dir(out_dir: Path) -> int:
    """清空输出目录下的全部内容（切片前调用）。

    安全措施：
    - 目录不存在或为空时直接返回 0（不报错）；
    - 防误删护栏：拒绝清空文件系统根目录、用户主目录、当前工作目录
      本身等危险路径；
    - 返回删除的条目数量，供调用方打印。
    """
    out_dir = Path(out_dir).resolve()
    if not out_dir.exists():
        return 0

    # ── 危险路径护栏 ──
    dangerous = {Path(out_dir.anchor).resolve(), Path.home().resolve(),
                 Path.cwd().resolve()}
    if out_dir in dangerous:
        raise ValueError(f"拒绝清空危险路径: {out_dir}")
    if len(out_dir.parts) <= 2:  # 如 C:\\Users 这类过浅路径
        raise ValueError(f"拒绝清空过浅的路径: {out_dir}")

    entries = list(out_dir.iterdir())
    for entry in entries:
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    return len(entries)

# Same token pattern as core.stylometry.tokenize.
_TOKEN_RE = re.compile(TOKEN_PATTERN)


def chunk_text(text: str, chunk_size: int = 2000) -> List[str]:
    """Split ``text`` into word-count chunks of ``chunk_size`` words.

    Words are matched with the same ``[A-Za-z]+`` regex used by
    ``core.stylometry.tokenize``. Cuts are made at token boundaries in the
    original text, so punctuation and whitespace inside a chunk are kept
    intact. A trailing remainder shorter than ``0.5 * chunk_size`` words
    is dropped; otherwise it is kept as a final chunk.

    :param text: source English text
    :param chunk_size: target number of words per chunk
    :return: list of chunk strings (may be empty for very short texts)
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")

    ends = [m.end() for m in _TOKEN_RE.finditer(text)]
    if not ends:
        return []

    chunks: List[str] = []
    start_char = 0
    start_word = 0
    total_words = len(ends)

    while start_word < total_words:
        remaining = total_words - start_word
        if remaining < 0.5 * chunk_size:
            break  # tail too short: discard
        take = min(chunk_size, remaining)
        end_word = start_word + take
        end_char = ends[end_word - 1]
        chunks.append(text[start_char:end_char])
        start_char = end_char
        start_word = end_word

    return chunks


def slice_corpus(
    input_dir: Path, out_dir: Path, chunk_size: int = 2000,
    clean: bool = False,
    progress_callback=None,
) -> List[Path]:
    """Slice every ``.txt`` under ``input_dir`` into word-count chunks.

    The directory structure of ``input_dir`` is mirrored under ``out_dir``.
    Each chunk is written as ``{stem}__chunk{NNN}.txt`` (1-based,
    zero-padded to 3 digits) next to where the source file would live.

    :param input_dir: corpus root, searched recursively for ``*.txt``
    :param out_dir: output root (created if missing)
    :param chunk_size: target number of words per chunk
    :param clean: True 时切片开始前先清空 ``out_dir`` 下的旧内容
                  （带危险路径护栏，见 ``clean_output_dir``）
    :param progress_callback: 可选进度回调
        ``callback(current, total, stage_name)``，每处理完一个源文件调用一次
    :return: list of written chunk file paths
    """
    input_dir = Path(input_dir)
    out_dir = Path(out_dir)
    if clean and out_dir.exists():
        removed = clean_output_dir(out_dir)
        if removed:
            print(f"cleaned {removed} item(s) under {out_dir} before slicing")
    out_dir.mkdir(parents=True, exist_ok=True)

    sources = sorted(input_dir.rglob("*.txt"))
    total = len(sources)
    written: List[Path] = []
    for file_idx, src in enumerate(sources, start=1):
        rel = src.relative_to(input_dir)
        text = src.read_text(encoding="utf-8")
        chunks = chunk_text(text, chunk_size)
        if not chunks:
            print(f"warning: {rel} produced no chunks "
                  f"(below 0.5 x chunk-size), skipped", file=sys.stderr)
            continue
        target_dir = out_dir / rel.parent
        target_dir.mkdir(parents=True, exist_ok=True)
        for i, chunk in enumerate(chunks, start=1):
            out_path = target_dir / f"{src.stem}__chunk{i:03d}.txt"
            out_path.write_text(chunk, encoding="utf-8")
            written.append(out_path)
        print(f"  {rel}: {len(chunks)} chunk(s)")
        if progress_callback is not None:
            progress_callback(file_idx, total, "切片")
    return written


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Slice a corpus into fixed-size word chunks"
    )
    parser.add_argument("--input", required=True,
                        help="corpus directory (searched recursively for .txt)")
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument("--chunk-size", type=int, default=2000,
                        help="target words per chunk (default 2000)")
    parser.add_argument("--clean", action="store_true",
                        help="empty the output directory before slicing "
                             "(refuses dangerous paths)")
    args = parser.parse_args()

    if args.chunk_size <= 0:
        parser.error("--chunk-size must be a positive integer")

    input_dir = Path(args.input)
    if not input_dir.is_dir():
        print(f"error: input directory not found: {input_dir}",
              file=sys.stderr)
        sys.exit(1)

    print(f"Slicing {input_dir} (chunk-size={args.chunk_size}) ...")
    try:
        written = slice_corpus(input_dir, Path(args.out),
                               args.chunk_size, clean=args.clean)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Done: {len(written)} chunk file(s) written to {args.out}")


if __name__ == "__main__":
    main()
