"""GUI 冒烟测试:python tests/smoke_gui.py

启动主窗口 2.5 秒后自动退出,验证界面能正常构建(需要桌面环境)。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    QTimer.singleShot(2500, app.quit)
    rc = app.exec()
    print("GUI SMOKE OK" if rc == 0 else f"GUI exited with {rc}")
    sys.exit(0 if rc == 0 else 1)


if __name__ == "__main__":
    main()
