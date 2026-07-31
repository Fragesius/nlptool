"""便携路径管理。

所有数据文件（历史记录、API配置、缓存）统一存储方式：

  开发模式（python main.py）：
    软件目录 / _data /
      history.json
      api_config.json
      cache/

  PyInstaller 打包后（.exe）：
    EXE 所在目录 / _data /
      history.json
      api_config.json
      cache/

不再往用户主目录写任何文件，做到真正的"复制即用、删除即走"。
"""

from __future__ import annotations

import os
import sys


def _app_root() -> str:
    """返回软件根目录（可写）。"""
    if getattr(sys, "frozen", False):
        # PyInstaller 打包：EXE 所在目录
        return os.path.dirname(sys.executable)
    else:
        # 开发模式：以本文件所在目录向上推一级作为项目根
        # 避免依赖 os.getcwd()，确保从任意目录运行都能找到正确数据路径
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# 可写数据根目录
APP_ROOT = _app_root()
DATA_DIR = os.path.join(APP_ROOT, "_data")

# 各数据文件路径
HISTORY_PATH = os.path.join(DATA_DIR, "history.json")
API_CONFIG_PATH = os.path.join(DATA_DIR, "api_config.json")
SETUP_DONE_PATH = os.path.join(DATA_DIR, ".setup_done")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
JIEBA_CACHE = os.path.join(CACHE_DIR, "jieba.cache")


def ensure_data_dirs() -> None:
    """确保所有数据目录存在。首次运行或便携版解压后调用。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)

    # 在 CACHE_DIR 放一个说明文件
    readme = os.path.join(CACHE_DIR, "_README.txt")
    if not os.path.exists(readme):
        with open(readme, "w", encoding="utf-8") as f:
            f.write(
                "此目录用于存放运行时缓存文件（jieba 分词缓存等）。\n"
                "可以安全删除，下次运行会自动重建。\n"
            )


# 启动时自动初始化
ensure_data_dirs()


def is_first_run() -> bool:
    """首次运行（未完成过初始设置）时返回 True。"""
    return not os.path.exists(SETUP_DONE_PATH)


def mark_setup_done() -> None:
    """标记初始设置已完成，后续启动不再显示欢迎向导。"""
    ensure_data_dirs()
    with open(SETUP_DONE_PATH, "w") as f:
        f.write("1")


def migrate_from_old_location() -> int:
    """如果旧位置（~/.nlp_tool/）有历史数据，迁移到新位置。

    注意：只迁移历史记录，**绝不**自动迁移 API 密钥。
    API 密钥属于敏感凭证，用户应手动在新位置重新配置。

    Returns:
        迁移的条目数。如果没有旧数据则返回 0。
    """
    import json
    import shutil

    migrated = 0

    old_history = os.path.join(os.path.expanduser("~"), ".nlp_tool", "history.json")
    if os.path.exists(old_history) and not os.path.exists(HISTORY_PATH):
        try:
            shutil.copy2(old_history, HISTORY_PATH)
            with open(HISTORY_PATH, encoding="utf-8") as f:
                data = json.load(f)
            migrated += len(data) if isinstance(data, list) else 0
        except Exception:
            pass

    # 绝不自动迁移 API 密钥 —— 这是敏感凭证。
    # 如果旧位置有 api_config，提醒用户手动迁移（而非静默复制）。
    old_api = os.path.join(os.path.expanduser("~"), ".nlp_tool_api.json")
    if os.path.exists(old_api) and not os.path.exists(API_CONFIG_PATH):
        # 不复制，只在首次启动时提醒
        print(
            "[便携模式] 检测到旧位置的 API 配置，出于安全考虑未自动迁移。\n"
            "          如需使用在线 API，请在「设置 → API 配置」中重新填写。"
        )

    return migrated
