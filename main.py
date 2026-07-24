"""汉英 NLP 分析工具 — 便携版。

作者：Fragesius

数据全部存储在软件目录的 _data/ 下，不写入用户主目录。
复制整个文件夹即可迁移，删除即彻底清除。

运行：
    python main.py
"""

import os
import sys

# 确保包内导入（core / ui / viz）可用
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 便携数据目录初始化 & 旧数据迁移
from core._paths import ensure_data_dirs, migrate_from_old_location

ensure_data_dirs()
migrated = migrate_from_old_location()
if migrated:
    print(f"[便携模式] 从旧位置迁移了 {migrated} 条历史记录到 _data/")

from ui.main_window import main

if __name__ == "__main__":
    main()
