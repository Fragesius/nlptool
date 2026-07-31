"""轻量级测试运行器。

在未安装 pytest 时可直接运行：
    python run_tests.py
"""

import importlib
import inspect
import pkgutil
import sys
import traceback


def run_tests():
    import tests

    failed = 0
    passed = 0

    for finder, name, ispkg in pkgutil.iter_modules(tests.__path__):
        if not name.startswith("test_"):
            continue
        module = importlib.import_module(f"tests.{name}")
        for attr_name in dir(module):
            if not attr_name.startswith("test_"):
                continue
            func = getattr(module, attr_name)
            if not inspect.isfunction(func):
                continue
            try:
                func()
                print(f"  PASS  {name}.{attr_name}")
                passed += 1
            except Exception as e:
                print(f"  FAIL  {name}.{attr_name}")
                traceback.print_exc()
                failed += 1

    print(f"\n结果：{passed} 通过，{failed} 失败")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    run_tests()
