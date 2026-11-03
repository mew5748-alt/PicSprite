# -*- coding: utf-8 -*-
"""离屏渲染安装向导界面，用于检查布局（不需要真实桌面）。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "installer"))

from PySide6.QtCore import QTimer                              # noqa: E402
from PySide6.QtWidgets import QApplication                     # noqa: E402

import setup_main as S                                         # noqa: E402

OUT = os.path.join(ROOT, "tests", "shots", "09-setup.png")
original_exec = QApplication.exec


def fake_exec(*_a, **_k):
    """抢在事件循环阻塞前渲染一帧并截图。"""
    app = QApplication.instance()

    def shoot():
        tops = [w for w in app.topLevelWidgets() if w.isVisible()]
        for i, w in enumerate(tops):
            path = OUT if i == 0 else OUT.replace(".png", f"-{i}.png")
            w.grab().save(path)
            print(f"抓取 {w.windowTitle()!r} {w.width()}x{w.height()} -> {path}")
        app.quit()

    QTimer.singleShot(600, shoot)
    return original_exec()


QApplication.exec = fake_exec
S.run_gui()
print("完成")
