"""LiteSeal 入口。开发期直接 `python main.py` 运行。"""

import sys

from PySide6.QtWidgets import QApplication

from app import APP_NAME, __version__
from app.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    window = MainWindow()
    window.show()
    rc = app.exec()
    del window  # 先于解释器销毁 Qt 对象,避免个别环境下退出时段错误
    sys.exit(rc)


if __name__ == "__main__":
    main()
