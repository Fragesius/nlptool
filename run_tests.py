"""测试入口：委托 pytest。

等价于在仓库根目录运行：

    python -m pytest tests/

pytest 已在 requirements.txt 中声明。
"""

import pytest

if __name__ == "__main__":
    raise SystemExit(pytest.main(["tests/", "-q"]))
