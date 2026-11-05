# -*- coding: utf-8 -*-
"""身份证打印对话框的界面测试 + 截图。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPointF, QRectF, QTimer
from PySide6.QtGui import QFont, QTransform
from PySide6.QtWidgets import QApplication

from viewer import icons, imageio
from viewer.idcard import CARD_RATIO, IdCardOptions
from viewer.idcarddialog import CropDialog, IdCardDialog
from viewer.style import build_qss

HERE = os.path.dirname(os.path.abspath(__file__))
SHOTS = os.path.join(HERE, "shots")
os.makedirs(SHOTS, exist_ok=True)

app = QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)   # 对话框 accept 后还要继续跑导出步骤
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


front_path = os.path.join(HERE, "samples", "id-front.jpg")
back_path = os.path.join(HERE, "samples", "id-back.jpg")
front = imageio.load_qimage(front_path)
back = imageio.load_qimage(back_path)

opts = IdCardOptions(layout="vertical", gap_mm=18, margin_mm=10, copies=1)
dlg = IdCardDialog(front, front_path, back, back_path, opts)
dlg.resize(1000, 700)
dlg.show()


def step1():
    print("\n[1] 打开对话框")
    check("正面已裁剪", dlg.front is not None and dlg.front.width() > 400)
    check("反面已裁剪", dlg.back is not None and dlg.back.width() > 400)
    check("正面比例接近卡片",
          abs(dlg.front.width() / dlg.front.height() - CARD_RATIO) < 0.12,
          f"{dlg.front.width() / dlg.front.height():.2f}")
    check("预览已渲染", dlg.preview._pm is not None)
    check("打印按钮可用", dlg.btn_print.isEnabled())
    check("页面提示写的是实际尺寸", "85.6" in dlg.page_label.text(), dlg.page_label.text())
    check("打印机下拉框有内容", dlg.printer_row.box.count() >= 1)
    check("双面下拉框 3 项", dlg.printer_row.duplex.count() == 3)
    check("默认单面", dlg.printer_row.duplex_key() == "none")
    shot(dlg, "idcard-01-dialog.png")

    print("\n[2] 改选项")
    dlg.layout_box.setCurrentIndex(dlg.layout_box.findData("horizontal"))
    check("排列切换为左右", dlg.opts.layout == "horizontal")
    q = dlg.preview._pm
    dlg.gap_spin.setValue(8)
    check("间距写入选项", dlg.opts.gap_mm == 8)
    dlg.copies_spin.setValue(2)
    check("份数写入选项", dlg.opts.copies == 2)
    dlg._refresh_preview()
    check("提示显示 2 页", "2 页" in dlg.page_label.text(), dlg.page_label.text())

    print("\n[3] 双面设置")
    idx = dlg.printer_row.duplex.findData("long")
    dlg.printer_row.duplex.setCurrentIndex(idx)
    check("选项记录双面长边", dlg.opts.duplex == "long")
    from PySide6.QtPrintSupport import QPrinter
    check("打印机真的设成双面长边",
          dlg.printer.duplex() == QPrinter.DuplexMode.DuplexLongSide,
          str(dlg.printer.duplex()))

    dlg.copies_spin.setValue(1)
    dlg.layout_box.setCurrentIndex(dlg.layout_box.findData("vertical"))
    QTimer.singleShot(300, step_rotate)


def step_crop_start():
    print("\n[5] 手动调整裁剪")
    crop_dlg = CropDialog(front, dlg.slot_front.box, dlg)
    crop_dlg.resize(820, 620)
    crop_dlg.show()
    QTimer.singleShot(300, lambda: step_crop(crop_dlg))


def step_crop(crop_dlg):
    canvas = crop_dlg.canvas
    canvas._fit()
    # 直接摆一个已知的框：原图 100,100 起，宽 600 高 600/1.585
    w = 600.0
    h = w / CARD_RATIO
    canvas.set_rect(QRectF(100, 100, w, h))
    box = canvas.box()
    check("框选得到 CardBox", box is not None)
    check("框选比例锁定", abs(box.w / box.h - CARD_RATIO) < 0.01 if box else False)
    shot(crop_dlg, "idcard-03-crop.png")
    crop_dlg._accept()
    rb = crop_dlg.result_box
    check("确定后返回裁剪框", rb is not None)
    if rb:
        expect = w / crop_dlg._scale        # 对话框里显示的是缩小后的图
        check("坐标换算回原图", abs(rb.w - expect) < 6, f"{rb.w:.0f} vs {expect:.0f}")
        dlg.slot_front.set_box(rb)
        check("重新裁剪后正面更新", dlg.front.width() < 700, f"{dlg.front.width()}")
    QTimer.singleShot(300, step_final)


def _thumb(q):
    return list(imageio.pil_from_qimage(q).convert("L").resize((120, 76)).tobytes())


def _diff(a, b):
    return sum(abs(x - y) for x, y in zip(a, b)) / float(len(a))


def step_rotate():
    print("\n[4] 旋转")
    from viewer import idcard
    from viewer.idcard import CardBox

    # 基准：这张图正常放着的自动裁剪结果（第 4 步把正面手动框改小了，不能用它）
    base_crop, _ = idcard.auto_crop(front)

    # 把正面这张图倒过来，模拟「手机反着拍的一张身份证」
    turned = front.transformed(QTransform().rotate(180))
    dlg.slot_back.set_image(turned, "翻转.jpg")
    dlg._refresh_preview()
    check("倒置的图被自动转正", dlg.slot_back.rotation == 180, str(dlg.slot_back.rotation))
    d = _diff(_thumb(dlg.slot_back.crop()), _thumb(base_crop))
    check("转正后和正放的同一张图基本一致", d < 16, f"平均差 {d:.1f}")
    check("旋转按钮可用", dlg.slot_back.btn_cw.isEnabled()
          and dlg.slot_back.btn_ccw.isEnabled())
    check("状态里写明了旋转角度", "180" in dlg.slot_back.lb_state.text(),
          dlg.slot_back.lb_state.text())
    shot(dlg, "idcard-05-rotated.png")

    r0 = dlg.slot_back.rotation
    before = _thumb(dlg.slot_back.crop())
    dlg.slot_back.btn_cw.click()
    check("点顺时针 +90", dlg.slot_back.rotation == (r0 + 90) % 360,
          str(dlg.slot_back.rotation))
    check("转了之后画面真的变了", _diff(before, _thumb(dlg.slot_back.crop())) > 10)
    dlg.slot_back.btn_ccw.click()
    check("点逆时针转回来", dlg.slot_back.rotation == r0, str(dlg.slot_back.rotation))
    check("转回来画面复原", _diff(before, _thumb(dlg.slot_back.crop())) < 1.0)

    dlg.slot_back.btn_ccw.click()
    dlg.slot_back.btn_ccw.click()
    check("连按两次逆时针归零", dlg.slot_back.rotation == 0, str(dlg.slot_back.rotation))

    # 手动框选之后，旋转状态要保留下来
    dlg.slot_back.set_image(turned, "翻转.jpg")
    box = dlg.slot_back.box
    dlg.slot_back.set_box(CardBox(box.cx, box.cy, box.w, box.h, box.angle))
    check("重新框选后旋转保持", dlg.slot_back.rotation == 180,
          str(dlg.slot_back.rotation))

    # 换回正常的反面，后面的打印/导出用
    dlg.slot_back.set_image(back, back_path)
    dlg._refresh_preview()
    check("恢复正常反面后不再旋转", dlg.slot_back.rotation == 0)
    QTimer.singleShot(300, step_crop_start)


def step_final():
    print("\n[6] 打印入口")
    shot(dlg, "idcard-04-after-crop.png")
    dlg._do_print()
    check("点打印后对话框接受", dlg.result() == IdCardDialog.DialogCode.Accepted)
    check("返回的正面可用", dlg.front is not None)
    dlg.gap_spin.setValue(18)
    QTimer.singleShot(300, step_export)


def step_export():
    """导出 PDF 并渲染第一页，作为 README 的效果图（中间 PDF 放临时目录）。"""
    print("\n[7] 导出 PDF 效果图")
    import tempfile

    from PySide6.QtCore import QSize
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtPrintSupport import QPrinter

    from viewer import idcard

    tmp = os.path.join(tempfile.gettempdir(), "picsprite-idcard-test.pdf")
    pr = QPrinter(QPrinter.PrinterMode.HighResolution)
    # 第 4 步把正面手动改成了偏框，效果图要用自动识别的结果
    front_auto, _ = idcard.auto_crop(front)
    back_auto, _ = idcard.auto_crop(back)
    pages = idcard.export_pdf(pr, tmp, front_auto, back_auto, dlg.opts)
    check("导出 1 页", pages == 1, str(pages))

    doc = QPdfDocument()
    doc.load(tmp)
    check("PDF 可回读", doc.pageCount() == 1, str(doc.pageCount()))
    doc.render(0, QSize(760, 1075)).save(os.path.join(SHOTS, "idcard-02-pdf.png"))
    doc.close()
    try:
        os.remove(tmp)
    except OSError:
        pass

    print("\n" + "=" * 56)
    bad = [n for n, okv in results if not okv]
    print(f"通过 {len(results) - len(bad)} 项，失败 {len(bad)} 项   截图在 tests/shots/")
    if bad:
        print("失败：" + "、".join(bad))
    print("=" * 56)
    app.exit(0 if not bad else 1)


QTimer.singleShot(1100, step1)
sys.exit(app.exec())
