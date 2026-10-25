"""应用资源与跨打包环境的资源路径。"""

import os
import sys


def resource_path(rel: str) -> str:
    """开发环境返回项目根下的路径;PyInstaller 冻结后返回解包目录下的路径。"""
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, rel)
