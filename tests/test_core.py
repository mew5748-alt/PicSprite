# -*- coding: utf-8 -*-
"""核心图像能力自测：多格式读写、压缩到目标体积、批量操作。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtGui import QColor, QPainter, QImage
from PySide6.QtWidgets import QApplication

from viewer import imageio
from viewer.batch import BatchOptions, build_plan, execute_batch
from viewer.thumbcache import ThumbCache
from viewer import util

app = QApplication(sys.argv)


def make_photo(w=1600, h=1000):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    p = QPainter(img)
    for y in range(0, h, 4):
        c = QColor.fromHsv(int(200 * y / h), 200, 230)
        p.fillRect(0, y, w, 4, c)
    p.setPen(QColor("white"))
    f = p.font()
    f.setPointSize(90)
    p.setFont(f)
    p.drawText(img.rect(), 0x0084, "PicSprite 测试图")
    p.end()
    return img


tmp = tempfile.mkdtemp(prefix="picsprite_test_")
print("临时目录:", tmp)
base = make_photo()
src = os.path.join(tmp, "照片 测试.png")
imageio.write_bytes_atomic(src, imageio.encode_image(base, "PNG"))
print("原图:", os.path.getsize(src), "bytes")

# 1) 多格式另存
for fmt in ["JPEG", "PNG", "BMP", "TIFF", "WEBP", "GIF", "ICO"]:
    ext = imageio.FORMAT_BY_KEY[fmt].ext
    out = os.path.join(tmp, f"out_{fmt}{ext}")
    size, w, h, q = imageio.save_qimage_with_budget(base, out, fmt, 85)
    loaded = imageio.load_image(out)
    assert loaded.image is not None, f"{fmt} 写入后读不回来"
    print(f"  {fmt:5s} -> {size/1024:8.1f} KB  {w}x{h}  回读 {loaded.width}x{loaded.height} {loaded.fmt}")

# 2) 压缩到 120KB
r = imageio.compress_to_target(base, "JPEG", 120 * 1024, allow_resize=False)
print(f"压缩(不缩尺寸): {r.size/1024:.1f} KB q={r.quality} 达标={r.reached}")
r2 = imageio.compress_to_target(base, "JPEG", 40 * 1024, allow_resize=True)
print(f"压缩(允许缩小): {r2.size/1024:.1f} KB q={r2.quality} 尺寸={r2.width}x{r2.height} 达标={r2.reached}")

# 3) 旋转 / 翻转 / 缩放
rot = imageio.apply_transform(base, 90)
flip = imageio.apply_transform(base, 0, True, False)
assert (rot.width(), rot.height()) == (base.height(), base.width())
print("旋转后尺寸:", rot.width(), "x", rot.height())
nw, nh = imageio.fit_dimensions(1600, 1000, "long_edge", 800)
print("长边缩到 800 ->", nw, nh)
nw2, nh2 = imageio.resize_qimage(base, 400, 400).width(), imageio.resize_qimage(base, 400, 400).height()
print("指定 400x400 ->", nw2, nh2)

# 4) 缩略图 + 缓存
cache = ThumbCache(os.path.join(tmp, "_cache"), 50 * 1024 * 1024)
t = imageio.make_thumbnail(src, 172)
print("缩略图:", t.width(), t.height())
cache.put(src, 172, t)
assert cache.get(src, 172) is not None
print("缓存命中 OK, 缓存文件:", cache.count_files())

# 5) 批量
for i in range(4):
    imageio.save_qimage(base, os.path.join(tmp, f"batch_{i}.png"), "PNG", 80)
    imageio.save_qimage(base, os.path.join(tmp, f"batch_{i}.jpg"), "JPEG", 80)

files = [os.path.join(tmp, f"batch_{i}.png") for i in range(4)]
opts = BatchOptions(do_rename=True, pattern="旅行_{nn}", start_index=1, padding=2,
                    do_resize=True, resize_mode="long_edge", resize_val1=800,
                    out_mode="subfolder", subfolder="已处理")
plan = build_plan(files, opts)
for p in plan:
    print("  计划:", os.path.basename(p.src), "->", os.path.basename(p.dst), p.action, p.status)
summary = execute_batch(files, opts)
print("批量结果:", summary["done"], "失败:", summary["failed"])
print("输出目录:", os.listdir(os.path.join(tmp, "已处理")))

# 6) 纯重命名
jpgs = [os.path.join(tmp, f"batch_{i}.jpg") for i in range(4)]
ropts = BatchOptions(do_rename=True, pattern="假期 {nn}", start_index=10, padding=3, out_mode="overwrite")
print("纯重命名:", execute_batch(jpgs, ropts)["done"], sorted(os.listdir(tmp))[:8])

print("human_size:", util.human_size(1234567), "| parse:", util.parse_size_text("1.5MB"))
print("\n全部核心测试通过 ✅")
