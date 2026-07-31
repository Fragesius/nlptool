"""应用日志配置。

所有日志写入 ``_data/app.log``，便于非技术用户排查问题。
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from core._paths import DATA_DIR, ensure_data_dirs


def setup_logging() -> logging.Logger:
    """配置并返回应用日志记录器。"""
    ensure_data_dirs()
    log_path = os.path.join(DATA_DIR, "app.log")

    logger = logging.getLogger("nlptool")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        # 文件日志：最多 5 MB，保留 3 个备份
        file_handler = RotatingFileHandler(
            log_path, maxBytes=5 * 1024 * 1024, backupCount=3,
            encoding="utf-8"
        )
        file_handler.setLevel(logging.INFO)
        file_format = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)

        # 控制台日志（仅警告及以上）
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(file_format)
        logger.addHandler(console_handler)

    return logger


logger = setup_logging()
