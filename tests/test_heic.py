# -*- coding: utf-8 -*-
"""HEIC / HEIF（iPhone 默认格式）支持自测。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication

from viewer import imageio

app = QApplication(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "samples", "sample-heic.heic")

ok = 0
fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [OK] {name}")
    else:
        fail += 1
        print(f"  [!!] {name} {extra}")


print("\n[1] 解码器注册")
check("pillow-heif 可用", imageio.HEIF_AVAILABLE)
check(".heic 在可读后缀里", ".heic" in imageio.READABLE_EXTS)
check(".heif 在可读后缀里", ".heif" in imageio.READABLE_EXTS)
check("is_image_file 认得 .heic", imageio.is_image_file("照片.HEIC"))
check("格式名显示为 HEIC", imageio.format_label("HEIF") == "HEIC")
check("按扩展名显示 HEIC", imageio.format_label("/a/b/c.heic") == "HEIC")

print("\n[2] 读文件")
loaded = imageio.load_image(SAMPLE)
check("没有报错", not loaded.error and loaded.image is not None, loaded.error)
check("尺寸正确", loaded.width == 1600 and loaded.height == 1200,
      f"{loaded.width}x{loaded.height}")
check("格式识别为 HEIF", loaded.fmt == "HEIF", loaded.fmt)
check("像素不是空白",
      loaded.image is not None and loaded.image.pixelColor(800, 600).blue() > 100)

thumb = imageio.make_thumbnail(SAMPLE, 120)
check("缩略图可用", thumb is not None and not thumb.isNull())
check("缩略图没超过限制", thumb is not None and max(thumb.width(), thumb.height()) <= 120)

print("\n[3] 写出 HEIC")
img = loaded.image
data = imageio.encode_image(img, "HEIF", 82)
check("编码出字节", len(data) > 1000, str(len(data)))
check("HEIC 写进导出格式", any(f.key == "HEIF" for f in imageio.WRITE_FORMATS))

tmp = tempfile.mkdtemp(prefix="picsprite_heic_")
out = os.path.join(tmp, "转存.heic")
size, w, h, q = imageio.save_with_options(img, out, "HEIF", 82)
check("落盘成功", os.path.exists(out) and size > 1000)
back = imageio.load_image(out)
check("写出的 HEIC 能读回来", back.image is not None and not back.error, back.error)
check("尺寸保持一致", (back.width, back.height) == (1600, 1200),
      f"{back.width}x{back.height}")

print("\n[4] 压缩到指定体积")
import io

from PIL import Image

res = imageio.compress_to_target(img, "HEIF", 40000)
check("压缩结果不超过目标", res.size <= 40000, f"{res.size}")
try:
    probe = Image.open(io.BytesIO(res.data))
    decoded = probe.size[0] > 0
except Exception as exc:                                   # noqa: BLE001
    decoded = False
    print("     解码失败:", exc)
check("压缩后仍可解码", decoded)

print("\n" + "=" * 56)
print(f"通过 {ok} 项，失败 {fail} 项")
print("=" * 56)
sys.exit(0 if fail == 0 else 1)
