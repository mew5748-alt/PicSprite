# -*- coding: utf-8 -*-
"""看图精灵 启动入口。

用法：
    python main.py                # 打开上次的文件夹
    python main.py D:\\照片        # 打开文件夹
    python main.py D:\\a.jpg      # 打开单张图片
"""
from __future__ import annotations

import os
import sys

# 让 "python main.py" 在任何工作目录下都能找到 viewer 包
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from viewer import icons
from viewer.config import APP_NAME, APP_VERSION, ORGANIZATION
from viewer.mainwindow import MainWindow
from viewer.style import build_qss


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(ORGANIZATION)
    app.setStyle("Fusion")
    app.setWindowIcon(icons.app_icon())

    font = QFont("Microsoft YaHei UI")
    font.setPointSize(9)
    app.setFont(font)
    app.setStyleSheet(build_qss())

    start = sys.argv[1] if len(sys.argv) > 1 else None
    win = MainWindow(start)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
