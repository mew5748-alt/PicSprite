# -*- coding: utf-8 -*-
"""身份证打印自测：自动裁剪、A4 实际尺寸排版、页数、单双面。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication

from viewer import idcard, imageio, printing
from viewer.idcard import CardBox, IdCardOptions

app = QApplication(sys.argv)
HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "samples")

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


def solid(color, w=600, h=378):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    return img


def render(pdf_path, index=0, size=(760, 1075)):
    doc = QPdfDocument()
    doc.load(pdf_path)
    n = doc.pageCount()
    img = doc.render(index, QSize(*size)).convertToFormat(QImage.Format.Format_RGB32)
    doc.close()
    return n, img


def bbox_of(img, color: QColor, tol=24):
    xs, ys = [], []
    for y in range(0, img.height(), 2):
        for x in range(0, img.width(), 2):
            c = QColor(img.pixel(x, y))
            if (abs(c.red() - color.red()) <= tol and abs(c.green() - color.green()) <= tol
                    and abs(c.blue() - color.blue()) <= tol):
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


tmp = tempfile.mkdtemp(prefix="picsprite_idcard_")

# ---------------------------------------------------------------- 1. 自动裁剪
print("\n[1] 自动裁剪")
front_img = imageio.load_qimage(os.path.join(SAMPLES, "id-front.jpg"))
back_img = imageio.load_qimage(os.path.join(SAMPLES, "id-back.jpg"))
flat_img = imageio.load_qimage(os.path.join(SAMPLES, "id-flat.jpg"))
empty_img = imageio.load_qimage(os.path.join(SAMPLES, "id-empty.jpg"))

b_front = idcard.detect_card_box(front_img)
check("桌面上的卡片被识别出来", b_front.auto)
check("正面比例接近 1.585", abs(b_front.w / b_front.h - idcard.CARD_RATIO) < 0.12,
      f"{b_front.w / b_front.h:.2f}")
check("正面尺寸接近卡片实际大小", 760 < b_front.w < 900 and 470 < b_front.h < 570,
      f"{b_front.w:.0f}x{b_front.h:.0f}")
check("识别出倾斜角", 3 < abs(b_front.angle) < 9, f"{b_front.angle:.1f}°")

b_back = idcard.detect_card_box(back_img)
check("白纸上的卡片被识别出来", b_back.auto)
check("反面比例接近 1.585", abs(b_back.w / b_back.h - idcard.CARD_RATIO) < 0.12,
      f"{b_back.w / b_back.h:.2f}")
check("反面尺寸接近卡片实际大小", 740 < b_back.w < 900,
      f"{b_back.w:.0f}x{b_back.h:.0f}")

b_flat = idcard.detect_card_box(flat_img)
check("已经是卡片比例 -> 直接用整图", b_flat.w == flat_img.width()
      and b_flat.h == flat_img.height())

b_empty = idcard.detect_card_box(empty_img)
check("没卡片的空桌面 -> 回退并标记", not b_empty.auto)
check("回退框仍是卡片比例",
      abs(b_empty.w / b_empty.h - idcard.CARD_RATIO) < 0.05,
      f"{b_empty.w / b_empty.h:.2f}")

crop = idcard.crop_card(front_img, b_front)
check("裁剪结果非空", not crop.isNull())
check("裁剪后比例接近卡片", abs(crop.width() / crop.height() - idcard.CARD_RATIO) < 0.12,
      f"{crop.width() / crop.height():.2f}")
check("裁剪后像素变少", crop.width() < front_img.width())

# 倾斜的卡片要摆正：转正后内容的上下边应当水平
crop_empty = idcard.crop_card(empty_img, b_empty)
check("回退裁剪可用", not crop_empty.isNull())

# ---------------------------------------------------------------- 2. 版面计算
print("\n[2] A4 版面")
canvas = idcard.QRectF(0, 0, 190 * 4, 277 * 4)          # 4 px/mm
opts = IdCardOptions(layout="vertical", gap_mm=18, margin_mm=10)
slots = idcard.slots(canvas, opts, 4, True, True)
check("正反面各一张", len(slots) == 2)
(r1, w1), (r2, w2) = slots
check("上面是正面、下面是反面", w1 == "front" and w2 == "back")
check("卡片宽 85.6mm", abs(r1.width() - 85.6 * 4) < 0.5, f"{r1.width() / 4:.1f}mm")
check("卡片高 54mm", abs(r1.height() - 54 * 4) < 0.5, f"{r1.height() / 4:.1f}mm")
check("两张卡水平居中对齐", abs(r1.center().x() - r2.center().x()) < 0.1)
check("间距 18mm", abs((r2.top() - r1.bottom()) / 4 - 18) < 0.1,
      f"{(r2.top() - r1.bottom()) / 4:.1f}mm")
check("整体垂直居中",
      abs((r1.top() + r2.bottom()) / 2 - canvas.center().y()) < 0.5)
check("两张卡都在可打印区内", canvas.contains(r1) and canvas.contains(r2))

opts_h = IdCardOptions(layout="horizontal", gap_mm=10, margin_mm=10)
sh = idcard.slots(canvas, opts_h, 4, True, True)
check("左右排列同高", abs(sh[0][0].top() - sh[1][0].top()) < 0.1)
check("左右排列间距 10mm", abs((sh[1][0].left() - sh[0][0].right()) / 4 - 10) < 0.1)
check("左右排列仍在纸张内", canvas.contains(sh[0][0]) and canvas.contains(sh[1][0]))

# 间距大到放不下时应当自动压缩，而不是溢出纸张
opts_h2 = IdCardOptions(layout="horizontal", gap_mm=40, margin_mm=10)
sh2 = idcard.slots(canvas, opts_h2, 4, True, True)
check("间距过大自动压缩", (sh2[1][0].left() - sh2[0][0].right()) / 4 < 40)
check("压缩后仍不出纸张", canvas.contains(sh2[0][0]) and canvas.contains(sh2[1][0]))

one = idcard.slots(canvas, opts, 4, True, False)
check("只有一面时只画一张", len(one) == 1)
check("单张时居中", abs(one[0][0].center().y() - canvas.center().y()) < 0.5)

# ---------------------------------------------------------------- 3. 导出 PDF
print("\n[3] 导出与物理尺寸")
red = solid("#d02020", 856, 540)
blue = solid("#2050c0", 856, 540)
opts_pdf = IdCardOptions(layout="vertical", gap_mm=18, margin_mm=10, copies=1)
pr = QPrinter(QPrinter.PrinterMode.HighResolution)
printing.ensure_a4(pr)
pdf = os.path.join(tmp, "idcard.pdf")
n = idcard.export_pdf(pr, pdf, red, blue, opts_pdf)
check("导出 1 页", n == 1)
pages, img = render(pdf)
check("PDF 实际 1 页", pages == 1)
check("纸张是 A4", abs(printing.paper_mm(pr)[0] - 210) < 2)

rb = bbox_of(img, QColor("#d02020"))
bb = bbox_of(img, QColor("#2050c0"))
check("正面在页面上", rb is not None)
check("反面在页面上", bb is not None)
if rb and bb:
    cw = rb[2] - rb[0]
    ch = rb[3] - rb[1]
    exp_w = 85.6 / 210 * img.width()
    exp_h = 54.0 / 297 * img.height()
    check("卡片宽度 = 85.6mm", abs(cw - exp_w) < 10, f"{cw}px vs {exp_w:.0f}px")
    check("卡片高度 = 54mm", abs(ch - exp_h) < 10, f"{ch}px vs {exp_h:.0f}px")
    check("卡片水平居中", abs((rb[0] + rb[2]) / 2 - img.width() / 2) < 6)
    gap_px = bb[1] - rb[3]
    exp_gap = 18 / 297 * img.height()
    check("两卡间距 = 18mm", abs(gap_px - exp_gap) < 8, f"{gap_px}px vs {exp_gap:.0f}px")

# 左右排列
pdf_h = os.path.join(tmp, "idcard-h.pdf")
pr_h = QPrinter(QPrinter.PrinterMode.HighResolution)
printing.ensure_a4(pr_h)
idcard.export_pdf(pr_h, pdf_h, red, blue,
                  IdCardOptions(layout="horizontal", gap_mm=20, margin_mm=10))
_, imgh = render(pdf_h)
r1b = bbox_of(imgh, QColor("#d02020"))
b1b = bbox_of(imgh, QColor("#2050c0"))
check("左右排列同高", r1b and b1b and abs(r1b[1] - b1b[1]) < 6)
check("左右排列正面在左", r1b and b1b and r1b[0] < b1b[0])

# 份数
pdf3 = os.path.join(tmp, "idcard-3.pdf")
pr3 = QPrinter(QPrinter.PrinterMode.HighResolution)
printing.ensure_a4(pr3)
check("份数 3 返回 3 页",
      idcard.export_pdf(pr3, pdf3, red, blue, IdCardOptions(copies=3)) == 3)
p3, _ = render(pdf3)
check("PDF 实际 3 页", p3 == 3)

# 只有一面
pdf_one = os.path.join(tmp, "idcard-one.pdf")
pr_one = QPrinter(QPrinter.PrinterMode.HighResolution)
printing.ensure_a4(pr_one)
idcard.export_pdf(pr_one, pdf_one, red, None, IdCardOptions())
_, img1 = render(pdf_one)
one_b = bbox_of(img1, QColor("#d02020"))
check("只有一面也能导出", one_b is not None)
check("单面卡片垂直居中",
      one_b and abs((one_b[1] + one_b[3]) / 2 - img1.height() / 2) < 6)

# 空数据
check("两面都没有 -> 0 页",
      idcard.draw_document(QPrinter(), None, None, IdCardOptions()) == 0)

# ---------------------------------------------------------------- 4. 单双面
print("\n[4] 单双面设置")
pd = QPrinter(QPrinter.PrinterMode.HighResolution)
printing.apply_duplex(pd, "none")
check("单面", pd.duplex() == QPrinter.DuplexMode.DuplexNone)
printing.apply_duplex(pd, "long")
check("双面长边", pd.duplex() == QPrinter.DuplexMode.DuplexLongSide)
printing.apply_duplex(pd, "short")
check("双面短边", pd.duplex() == QPrinter.DuplexMode.DuplexShortSide)
printing.apply_duplex(pd, "unknown")
check("未知值不报错", pd.isValid() is not None)

# ---------------------------------------------------------------- 5. 朝向与旋转
print("\n[5] 朝向与旋转")
from PIL import Image                                       # noqa: E402

rot_dir = os.path.join(tmp, "rot")
os.makedirs(rot_dir, exist_ok=True)


def thumb(q):
    return list(imageio.pil_from_qimage(q).convert("L").resize((120, 76)).tobytes())


def diff(a, b):
    return sum(abs(x - y) for x, y in zip(a, b)) / float(len(a))


check("正向的正面不再旋转", idcard.detect_upright(
    idcard.auto_crop(front_img)[0]) == 0)
check("正向的反面不再旋转", idcard.detect_upright(
    idcard.auto_crop(back_img)[0]) == 0)

for name in ("id-front", "id-back"):
    src = Image.open(os.path.join(SAMPLES, f"{name}.jpg")).convert("RGB")
    base = None
    for deg in (0, 90, 180, 270):
        p = os.path.join(rot_dir, f"{name}-{deg}.jpg")
        (src.rotate(-deg, expand=True) if deg else src).save(p, quality=93)
        crop, box = idcard.auto_crop(imageio.load_qimage(p))
        check(f"{name} 转 {deg}° 后仍是横向卡片", crop.width() > crop.height(),
              f"{crop.width()}x{crop.height()}")
        check(f"{name} 转 {deg}° 后摆正结果可复现", idcard.detect_upright(crop) == 0,
              f"rotation={box.rotation}")
        t = thumb(crop)
        if deg == 0:
            base = t
        else:
            d = diff(base, t)
            # 摆正后应当和正立的基准图基本一致；方向转错时会到 20 以上
            check(f"{name} 转 {deg}° 后内容是正立的", d < 15, f"与基准平均差 {d:.1f}")

# 把已经摆正的结果再人为转 180，差异必须明显变大，否则上面的判据没有区分力
sample = idcard.auto_crop(imageio.load_qimage(os.path.join(rot_dir, "id-front-180.jpg")))[0]
check("转错 180° 时差异显著变大",
      diff(thumb(sample), thumb(idcard.rotate_card(sample, 180))) > 18)

# rotate_card 的基本性质
rot90 = idcard.rotate_card(sample, 90)
check("转 90° 后宽高互换",
      rot90.width() == sample.height() and rot90.height() == sample.width(),
      f"{rot90.width()}x{rot90.height()}")
check("转 0° 原样返回", idcard.rotate_card(sample, 0) is sample)
check("转 360° 等同于不转",
      diff(thumb(sample), thumb(idcard.rotate_card(sample, 360))) < 0.5)
check("反转回去能还原",
      diff(thumb(sample), thumb(idcard.rotate_card(idcard.rotate_card(sample, 90), -90))) < 0.5)

# CardBox.rotation 与手工再转一次等价
box_r = CardBox(b_back.cx, b_back.cy, b_back.w, b_back.h, b_back.angle, rotation=180)
check("CardBox.rotation=180 与裁完再转一致",
      diff(thumb(idcard.crop_card(back_img, box_r)),
           thumb(idcard.rotate_card(idcard.crop_card(back_img, b_back), 180))) < 1.0)

print("\n" + "=" * 56)
print(f"通过 {ok} 项，失败 {fail} 项")
print("=" * 56)
sys.exit(0 if fail == 0 else 1)
