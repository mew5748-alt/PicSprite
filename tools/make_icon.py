# -*- coding: utf-8 -*-
"""用应用内绘制的图标生成 assets/app.ico（打包 exe 时使用）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image
from PySide6.QtWidgets import QApplication

from viewer import icons

app = QApplication(sys.argv)
icon = icons.app_icon()

out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
os.makedirs(out_dir, exist_ok=True)

frames = []
for size in (16, 24, 32, 48, 64, 128, 256):
    pm = icon.pixmap(size, size)
    img = pm.toImage().convertToFormat(pm.toImage().Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    buf = bytes(img.constBits())
    pil = Image.frombuffer("RGBA", (w, h), buf, "raw", "RGBA", img.bytesPerLine(), 1).copy()
    frames.append(pil)

path = os.path.join(out_dir, "app.ico")
frames[-1].save(path, format="ICO", sizes=[(f.width, f.height) for f in frames])
print("已生成:", path, os.path.getsize(path), "字节")
