"""测试包共享件：可选依赖可用性探测与 sample_corpus 路径。"""

from pathlib import Path


def has_matplotlib() -> bool:
    """matplotlib 是否可导入（不可用则相关测试跳过）。"""
    try:
        import matplotlib  # noqa: F401
        return True
    except ImportError:
        return False


def has_scipy() -> bool:
    """scipy 是否可导入（不可用则 scipy 对拍测试跳过）。"""
    try:
        import scipy.stats  # noqa: F401
        return True
    except ImportError:
        return False


_SAMPLE_DIR = Path(__file__).resolve().parent.parent / "experiments" / "sample_corpus"
