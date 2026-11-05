# -*- coding: utf-8 -*-
"""打印对话框的界面测试 + 截图。

与 test_gui 一样只用 QTimer 链推进，不用 QTest.qWait。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QFont, QImage
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication

from viewer import icons, printing
from viewer.printdialog import PrintDialog
from viewer.printing import PrintItem, PrintOptions
from viewer.style import build_qss

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, "shots")
os.makedirs(SHOTS, exist_ok=True)

app = QApplication(sys.argv)
app.setStyle("Fusion")
f = QFont("Microsoft YaHei UI")
f.setPointSize(9)
app.setFont(f)
app.setStyleSheet(build_qss())
app.setWindowIcon(icons.app_icon())

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond)))
    print(("  OK  " if cond else "  !!  ") + name + ((" | " + extra) if extra and not cond else ""))


def shot(widget, name):
    widget.grab().save(os.path.join(SHOTS, name))


def photo(hue, w=900, h=650):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    from PySide6.QtGui import QPainter
    p = QPainter(img)
    for y in range(0, h, 3):
        p.fillRect(0, y, w, 3, QColor.fromHsv((hue + int(60 * y / h)) % 360, 170, 235))
    p.end()
    return img


ITEMS = [PrintItem(photo(20 * i), f"照片 {i + 1}.jpg", f"2024-05-{i + 1:02d}") for i in range(6)]

opts = PrintOptions(per_page=1, scale="fit", margin_mm=6, gap_mm=4,
                    show_title=True, show_date=False)

scopes = [
    ("current", "当前图片", lambda: ITEMS[:1]),
    ("selected", f"选中的 {len(ITEMS)} 张图片", lambda: list(ITEMS)),
]


def printer():
    return QPrinter(QPrinter.PrinterMode.HighResolution)


dlg = PrintDialog(printer(), scopes, opts)
dlg.resize(940, 660)
dlg.show()

steps = []


def step(fn):
    steps.append(fn)


def first():
    print("\n[1] 对话框基本状态")
    check("窗口标题是「打印」", dlg.windowTitle() == "打印", dlg.windowTitle())
    check("预设有 6 张", len(ITEMS) == 6)
    check("范围下拉有 2 项", dlg.scope_box.count() == 2, str(dlg.scope_box.count()))
    check("排版下拉有 5 项", dlg.per_box.count() == 5, str(dlg.per_box.count()))
    check("缩放有 3 种", dlg.scale_box.count() == 3, str(dlg.scale_box.count()))
    check("默认范围是当前图片", dlg.scope_box.currentIndex() == 0)
    check("默认 1 张/页 -> 1 页", dlg.page_label.text() == "第 1 / 1 页", dlg.page_label.text())
    check("单页时翻页按钮禁用", not dlg.btn_prev.isEnabled() and not dlg.btn_next.isEnabled())
    check("打印按钮可用", dlg.btn_print.isEnabled())
    check("预览已渲染", dlg.preview._pm is not None and not dlg.preview._pm.isNull())


def snap1():
    shot(dlg, "print-01-dialog.png")


def second():
    print("\n[2] 切到 6 张 + 每页 4 张")
    dlg.scope_box.setCurrentIndex(1)
    dlg.per_box.setCurrentIndex(dlg.per_box.findData(4))
    check("共 6 张 -> 2 页", dlg.page_label.text() == "第 1 / 2 页", dlg.page_label.text())
    check("下一页可用", dlg.btn_next.isEnabled())
    dlg.btn_next.click()
    check("翻到第 2 页", dlg.page_label.text() == "第 2 / 2 页", dlg.page_label.text())
    check("第 2 页时上一页可用", dlg.btn_prev.isEnabled())
    dlg.btn_prev.click()
    check("翻回第 1 页", dlg.page_label.text() == "第 1 / 2 页", dlg.page_label.text())
    check("信息区写了张数", "6 张图片" in dlg.info.text() or "6" in dlg.info.text(),
          dlg.info.text().replace("\n", " / "))


def third():
    print("\n[3] 选项联动")
    dlg.scale_box.setCurrentIndex(dlg.scale_box.findData("fill"))
    dlg.cb_date.setChecked(True)
    dlg.margin_spin.setValue(12.0)
    dlg.gap_spin.setValue(8.0)
    dlg._refresh_preview()
    o = dlg.opts
    check("缩放 = fill", o.scale == "fill", o.scale)
    check("显示日期已开", o.show_date is True)
    check("页边距 = 12", abs(o.margin_mm - 12.0) < 1e-6, str(o.margin_mm))
    check("间距 = 8", abs(o.gap_mm - 8.0) < 1e-6, str(o.gap_mm))
    check("换选项后预览仍在", dlg.preview._pm is not None)


def snap2():
    shot(dlg, "print-02-4up.png")


def printerpick():
    print("\n[4] 打印机与单双面")
    check("有打印机下拉框", dlg.printer_row.box.count() >= 1)
    check("默认选中的是当前打印机",
          dlg.printer_row.box.currentText() == dlg.printer.printerName()
          or not dlg.printer.printerName(), dlg.printer_row.box.currentText())
    check("默认单面", dlg.printer_row.duplex_key() == "none")
    idx = dlg.printer_row.duplex.findData("short")
    dlg.printer_row.duplex.setCurrentIndex(idx)
    check("选项记录双面短边", dlg.opts.duplex == "short", dlg.opts.duplex)
    check("打印机设成双面短边",
          dlg.printer.duplex() == QPrinter.DuplexMode.DuplexShortSide,
          str(dlg.printer.duplex()))
    check("信息区标了双面", "双面" in dlg.info.text(), dlg.info.text().replace("\n", " / "))
    dlg.printer_row.duplex.setCurrentIndex(dlg.printer_row.duplex.findData("none"))
    check("切回单面", dlg.printer.duplex() == QPrinter.DuplexMode.DuplexNone)
    dlg._refresh_preview()
    print("\n[5] 9 张/页时的 2 张图")
    dlg.per_box.setCurrentIndex(dlg.per_box.findData(9))
    dlg._refresh_preview()
    check("9 张/页 6 张图 -> 1 页", dlg.page_label.text() == "第 1 / 1 页", dlg.page_label.text())


def snap3():
    shot(dlg, "print-03-9up.png")


def finish():
    print("\n[6] 无图时的降级")
    dlg._scopes = [("current", "当前图片", lambda: [])]
    dlg._load_scope(0)
    dlg._refresh_preview()
    check("没有图时打印按钮禁用", not dlg.btn_print.isEnabled())
    check("预览显示提示文字", dlg.preview._pm is None)

    good = sum(1 for _n, ok in results if ok)
    bad = len(results) - good
    print("\n" + "=" * 56)
    print(f"通过 {good} 项，失败 {bad} 项   截图在 tests/shots/")
    print("=" * 56)
    dlg.close()
    app.exit(0 if bad == 0 else 1)


CHAIN = [
    (250, first),
    (250, snap1),
    (700, second),
    (700, third),
    (700, snap2),
    (700, printerpick),
    (700, snap3),
    (500, finish),
]


def advance(i=0):
    if i >= len(CHAIN):
        return
    delay, fn = CHAIN[i]
    QTimer.singleShot(delay, lambda: (fn(), advance(i + 1)))


advance()
sys.exit(app.exec())
