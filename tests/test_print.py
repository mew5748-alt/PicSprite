# -*- coding: utf-8 -*-
"""打印功能自测：版面计算、PDF 导出页数、以及渲染出来的像素是否真的落在该在的位置。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage, QPageLayout, QPainter
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication

from viewer import printing
from viewer.printing import PrintItem, PrintOptions

app = QApplication(sys.argv)

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


tmp = tempfile.mkdtemp(prefix="picsprite_print_")

# ---------------------------------------------------------------- 纯色测试图
COLORS = {
    "red": "#d02020",
    "green": "#20a040",
    "blue": "#2050c0",
    "yellow": "#e8c020",
}


def solid(name, w=400, h=300):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor(COLORS[name]))
    return img


def near(a: QColor, b: QColor, tol=26) -> bool:
    return (abs(a.red() - b.red()) <= tol and abs(a.green() - b.green()) <= tol
            and abs(a.blue() - b.blue()) <= tol)


# ---------------------------------------------------------------- 1. 版面计算
print("\n[1] 版面计算")
check("1 张 -> 1x1", printing.grid_for(1, False) == (1, 1))
check("2 张 纵向 -> 1 列 2 行", printing.grid_for(2, False) == (1, 2))
check("2 张 横向 -> 2 列 1 行", printing.grid_for(2, True) == (2, 1))
check("4 张 -> 2x2", printing.grid_for(4, False) == (2, 2))
check("6 张 纵向 -> 2x3", printing.grid_for(6, False) == (2, 3))
check("6 张 横向 -> 3x2", printing.grid_for(6, True) == (3, 2))
check("9 张 -> 3x3", printing.grid_for(9, False) == (3, 3))
check("0 张兜底 1x1", printing.grid_for(0, False) == (1, 1))

for n in (1, 2, 4, 6, 9):
    c, r = printing.grid_for(n, False)
    check(f"{n} 张的格子数 {c}x{r} >= {n}", c * r >= n)

print("\n[2] 页数")
check("0 张 -> 0 页", printing.page_count(0, 1) == 0)
check("1 张/页 x 3 -> 3 页", printing.page_count(3, 1) == 3)
check("4 张/页 x 9 -> 3 页", printing.page_count(9, 4) == 3)
check("4 张/页 x 10 -> 3 页", printing.page_count(10, 4) == 3)
check("6 张/页 x 6 -> 1 页", printing.page_count(6, 6) == 1)


# ---------------------------------------------------------------- 3. 渲 PDF
def render(path, index=0, size=(620, 877)):
    """按 PDF 阅读器的方式渲染：透明像素合成到白纸上。"""
    doc = QPdfDocument()
    doc.load(path)
    n = doc.pageCount()
    raw = doc.render(index, QSize(*size))
    doc.close()
    if raw.isNull():
        return n, raw
    img = QImage(raw.size(), QImage.Format.Format_RGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    p.drawImage(0, 0, raw)
    p.end()
    return n, img


def export(items, opts, name):
    path = os.path.join(tmp, name)
    pr = QPrinter(QPrinter.PrinterMode.HighResolution)
    printing.export_pdf(pr, path, items, opts)
    return path


print("\n[3] 单张导出与像素位置")
opts = PrintOptions(per_page=1, scale="fit", margin_mm=8, gap_mm=4,
                    show_title=False, show_date=False)
items = [PrintItem(solid("red"), "red.png", "")]
p1 = export(items, opts, "one.pdf")
n, img = render(p1)
check("文件已生成", os.path.exists(p1) and os.path.getsize(p1) > 1000,
      f"{os.path.getsize(p1) if os.path.exists(p1) else 0} bytes")
check("页数为 1", n == 1, f"实际 {n}")
c = QColor(img.pixel(img.width() // 2, img.height() // 2))
check("页面中心是红色", near(c, QColor(COLORS["red"])), c.name())
c2 = QColor(img.pixel(4, 4))
check("页面角落是白纸（页边距生效）", c2.lightness() > 230, f"{c2.name()} L={c2.lightness()}")


print("\n[4] 4 张/页的象限归属")
four = [PrintItem(solid("red"), "a.png", ""),
        PrintItem(solid("green"), "b.png", ""),
        PrintItem(solid("blue"), "c.png", ""),
        PrintItem(solid("yellow"), "d.png", "")]
opts4 = PrintOptions(per_page=4, scale="fit", margin_mm=6, gap_mm=4,
                     show_title=False, show_date=False)
p4 = export(four, opts4, "four.pdf")
n4, img4 = render(p4)
check("4 张 1 页", n4 == 1, f"实际 {n4}")

w, h = img4.width(), img4.height()
pts = {
    "左上=red": (w * 0.27, h * 0.27, "red"),
    "右上=green": (w * 0.73, h * 0.27, "green"),
    "左下=blue": (w * 0.27, h * 0.73, "blue"),
    "右下=yellow": (w * 0.73, h * 0.73, "yellow"),
}
for label, (x, y, key) in pts.items():
    c = QColor(img4.pixel(int(x), int(y)))
    check(label, near(c, QColor(COLORS[key])), f"实际 {c.name()}")

# 象限之间不应串图：中心竖线附近应该是纸白
mid = QColor(img4.pixel(w // 2, h // 2))
check("中线留白（格子不重叠）", mid.lightness() > 230, mid.name())


print("\n[5] 分页")
many = [PrintItem(solid("blue"), f"{i}.png", "") for i in range(5)]
opts2 = PrintOptions(per_page=2, scale="fit", margin_mm=6, gap_mm=4,
                     show_title=False, show_date=False)
p5 = export(many, opts2, "five.pdf")
n5, _img5 = render(p5)
check("5 张 2 张/页 -> 3 页", n5 == 3, f"实际 {n5}")
print("  说明：最后一页只有 1 张，其余格子留空")


print("\n[6] 铺满模式")
optsf = PrintOptions(per_page=4, scale="fill", margin_mm=6, gap_mm=0,
                     show_title=False, show_date=False)
pf = export([PrintItem(solid("red"), "r.png", "")], optsf, "fill.pdf")
_nf, imgf = render(pf)
w2, h2 = imgf.width(), imgf.height()
# 铺满且间距 0：左上格子范围内靠边处也应是图片颜色
c = QColor(imgf.pixel(int(w2 * 0.12), int(h2 * 0.12)))
check("铺满模式覆盖到格子边缘", near(c, QColor(COLORS["red"])), c.name())


print("\n[7] 标题与日期")
optsc = PrintOptions(per_page=1, scale="fit", margin_mm=8, gap_mm=4,
                     show_title=True, show_date=True)
pc = export([PrintItem(solid("green"), "风景照片.png", "2024-05-01 10:22")], optsc, "cap.pdf")
_nc, imgc = render(pc)


def neutral_dark(c: QColor) -> bool:
    """灰色文字像素：三个通道接近且偏暗（纯色图片不会被误判）。"""
    spread = max(c.red(), c.green(), c.blue()) - min(c.red(), c.green(), c.blue())
    return spread < 26 and c.lightness() < 150


dark = sum(1 for y in range(int(imgc.height() * 0.45), int(imgc.height() * 0.99), 2)
           for x in range(int(imgc.width() * 0.25), int(imgc.width() * 0.75), 2)
           if neutral_dark(QColor(imgc.pixel(x, y))))
check("图注文字已绘制", dark > 20, f"深色文字像素 {dark}")

# 图注应紧贴图片下沿：图片下沿往下 3mm 内就能找到文字
img_bottom_px = None
for y in range(int(imgc.height() * 0.9), 0, -1):
    if near(QColor(imgc.pixel(imgc.width() // 2, y)), QColor(COLORS["green"])):
        img_bottom_px = y
        break
if img_bottom_px:
    band = range(img_bottom_px + 2, min(imgc.height(), img_bottom_px + 30))
    near_txt = any(neutral_dark(QColor(imgc.pixel(x, y)))
                   for y in band for x in range(int(imgc.width() * 0.3),
                                                int(imgc.width() * 0.7), 2))
    check("图注紧跟图片下沿", near_txt, f"图片下沿 y={img_bottom_px}")
else:
    check("图注紧跟图片下沿", False, "没找到图片下沿")


print("\n[8] 空数据")
check("空列表 -> 0 页", printing.page_count(0, 4) == 0)
pr_e = QPrinter(QPrinter.PrinterMode.HighResolution)
path_e = os.path.join(tmp, "empty.pdf")
check("空数据导出返回 0 页", printing.export_pdf(pr_e, path_e, [], opts) == 0)


print("\n[9] 预览图")
optsv = PrintOptions(per_page=4, scale="fit", margin_mm=6, gap_mm=4,
                     show_title=True, show_date=False)
prv = QPrinter(QPrinter.PrinterMode.HighResolution)
printing.apply_margins(prv, optsv.margin_mm)
pv = printing.preview_image(prv, four, optsv, 0, (720, 860))
check("预览图非空", pv is not None and not pv.isNull())
ratio = pv.width() / max(1, pv.height())
check("预览图接近 A4 比例 0.707", 0.66 < ratio < 0.75, f"实际 {ratio:.3f}")
pw, ph = printing.paper_mm(prv)
check("纸张尺寸合理", 100 < pw < 400 and 100 < ph < 500, f"{pw:.0f}x{ph:.0f}mm")

print("\n" + "=" * 56)
print(f"通过 {ok} 项，失败 {fail} 项")
print("=" * 56)
sys.exit(0 if fail == 0 else 1)
