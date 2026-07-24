"""构建便携版分发包。

用法：
    python build_portable.py

步骤：
    1. PyInstaller 打包 → dist/汉英NLP分析工具/
    2. 组装便携版文件夹
    3. 创建干净的 _data/（不包含任何运行时隐私数据）
    4. 输出到 dist/汉英NLP分析工具_便携版/
"""

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(ROOT, "dist")
BUILD_OUTPUT = os.path.join(DIST_DIR, "汉英NLP分析工具")  # PyInstaller 输出
PORTABLE_DIR = os.path.join(DIST_DIR, "汉英NLP分析工具_便携版")
SPEC_FILE = os.path.join(ROOT, "汉英NLP分析工具.spec")


def run_pyinstaller():
    """运行 PyInstaller 打包。"""
    print("[1/4] PyInstaller 打包中...")
    subprocess.check_call(
        [sys.executable, "-m", "PyInstaller", "--clean", SPEC_FILE],
        cwd=ROOT,
    )
    if not os.path.isdir(BUILD_OUTPUT):
        sys.exit(f"错误：PyInstaller 输出目录不存在: {BUILD_OUTPUT}")
    print(f"  完成 → {BUILD_OUTPUT}")


def assemble_portable():
    """复制 PyInstaller 输出到便携版文件夹。"""
    print("[2/4] 组装便携版文件夹...")
    if os.path.exists(PORTABLE_DIR):
        shutil.rmtree(PORTABLE_DIR)
    shutil.copytree(BUILD_OUTPUT, PORTABLE_DIR)
    print(f"  完成 → {PORTABLE_DIR}")


def create_clean_data():
    """创建干净的 _data/ 目录：只含必要结构，绝无隐私数据。"""
    print("[3/4] 创建干净的 _data/ 目录...")

    data_dir = os.path.join(PORTABLE_DIR, "_data")
    os.makedirs(data_dir, exist_ok=True)

    # 缓存目录
    cache_dir = os.path.join(data_dir, "cache")
    os.makedirs(cache_dir, exist_ok=True)

    # README（非敏感说明文件）
    readme_path = os.path.join(cache_dir, "_README.txt")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(
            "此目录用于存放运行时缓存文件（jieba 分词缓存等）。\n"
            "可以安全删除，下次运行会自动重建。\n"
        )

    # 坚决不写 history.json / api_config.json！
    # 这些文件由程序在首次运行时自动创建，不应随分发包附带。

    print(f"  完成 — 只含 cache/ 和说明文件")


def verify_portable():
    """最终检查：确保便携版中不含隐私数据。"""
    print("[4/4] 验证便携版不含隐私数据...")

    checks = [
        ("history.json", "历史记录"),
        ("api_config.json", "API 配置"),
        (".setup_done", "设置标记"),
    ]

    for filename, desc in checks:
        path = os.path.join(PORTABLE_DIR, "_data", filename)
        if os.path.exists(path):
            print(f"  ⚠ 警告：{desc} 文件仍存在，正在删除...")
            os.remove(path)

    print("  验证通过 ✓")


def main():
    os.chdir(ROOT)

    run_pyinstaller()
    assemble_portable()
    create_clean_data()
    verify_portable()

    print(f"\n✅ 便携版构建完成：{PORTABLE_DIR}")
    print("   可直接压缩该文件夹分发。数据目录已清空，不包含任何隐私信息。")


if __name__ == "__main__":
    main()
