# -*- coding: utf-8 -*-
"""身份证打印对话框：选正反面 → 自动裁成卡片 → A4 实际尺寸排版 → 打印 / 导出 PDF。"""
from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QImage, QPainter, QPainterPath, QPen,
                           QPixmap)
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                               QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QMessageBox, QPushButton, QSizePolicy, QSpinBox,
                               QVBoxLayout, QWidget)

from . import idcard, imageio, printing
from .idcard import CARD_H_MM, CARD_RATIO, CARD_W_MM, CardBox, IdCardOptions
from .printdialog import PagePreview
from .printerui import PrinterRow

IMAGE_FILTER = "图片 (*" + " *".join(imageio.READABLE_EXTS) + ");;所有文件 (*.*)"


class CardThumb(QWidget):
    """按卡片比例显示裁剪结果。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pm: Optional[QPixmap] = None
        self.setFixedSize(152, 96)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_image(self, img: Optional[QImage]) -> None:
        self._pm = QPixmap.fromImage(img) if img is not None and not img.isNull() else None
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setBrush(QColor("#f4f6fa"))
        p.setPen(QPen(QColor("#dde2ea"), 1))
        p.drawRoundedRect(r, 4, 4)
        if self._pm is None:
            p.setPen(QColor("#9aa3b2"))
            f = QFont(printing.FONT_FAMILY)
            f.setPointSize(8)
            p.setFont(f)
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), "未选择")
            return
        p.save()
        p.setClipRect(r.adjusted(1, 1, -1, -1))
        p.drawPixmap(r.adjusted(1, 1, -1, -1), self._pm, QRectF(self._pm.rect()))
        p.restore()


class CardSlot(QWidget):
    """一张卡：缩略图 + 状态 + 两个按钮。"""

    changed = Signal()

    def __init__(self, title: str, hint: str, parent=None) -> None:
        super().__init__(parent)
        self.original: Optional[QImage] = None
        self.path = ""
        self.box: Optional[CardBox] = None
        self._crop: Optional[QImage] = None

        self.lb_title = QLabel(title)
        self.lb_title.setStyleSheet("font-weight:600;")
        self.thumb = CardThumb()
        self.lb_state = QLabel(hint)
        self.lb_state.setObjectName("subtitle")
        self.lb_state.setWordWrap(True)

        self.btn_pick = QPushButton("选择图片…")
        self.btn_pick.clicked.connect(self._choose)
        self.btn_adjust = QPushButton("调整裁剪…")
        self.btn_adjust.clicked.connect(self._adjust)
        self.btn_adjust.setEnabled(False)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(4)
        right.addWidget(self.lb_state, 1)
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(self.btn_pick)
        row.addWidget(self.btn_adjust)
        right.addLayout(row)

        body = QHBoxLayout(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)
        body.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignTop)
        body.addLayout(right, 1)

    # ------------------------------------------------------------ 数据
    def crop(self) -> Optional[QImage]:
        return self._crop

    def set_image(self, img: Optional[QImage], path: str = "") -> None:
        self.original = img
        self.path = path
        self.box = None
        self._crop = None
        if img is None or img.isNull():
            self.thumb.set_image(None)
            self.lb_state.setText("未选择")
            self.btn_adjust.setEnabled(False)
            self.changed.emit()
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            box = idcard.detect_card_box(img)
            crop = idcard.crop_card(img, box)
        finally:
            QApplication.restoreOverrideCursor()
        self.box = box
        self._crop = crop
        self.thumb.set_image(crop)
        self.btn_adjust.setEnabled(True)
        self._update_state()

    def set_box(self, box: CardBox) -> None:
        if self.original is None:
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            crop = idcard.crop_card(self.original, box)
        finally:
            QApplication.restoreOverrideCursor()
        self.box = box
        self._crop = crop
        self.thumb.set_image(crop)
        self._update_state()
        self.changed.emit()

    def _update_state(self) -> None:
        name = os.path.basename(self.path) if self.path else ""
        head = f"{name}\n" if name else ""
        if self.box is None:
            self.lb_state.setText("未选择")
        elif self.box.auto and self.box.confidence >= 0.55:
            self.lb_state.setText(f"{head}已自动识别卡片边界")
        elif self.box.auto:
            self.lb_state.setText(f"{head}已自动裁剪\n有偏差可点「调整裁剪」")
        else:
            self.lb_state.setText(f"{head}未识别到边界，已居中裁剪\n点「调整裁剪」可手动框选")

    # ------------------------------------------------------------ 交互
    def _choose(self) -> None:
        start = os.path.dirname(self.path) if self.path else ""
        path, _ = QFileDialog.getOpenFileName(self, "选择身份证照片", start, IMAGE_FILTER)
        if not path:
            return
        loaded = imageio.load_image(path, max_frames=1)
        if loaded.image is None:
            QMessageBox.warning(self, "打不开这张图片", loaded.error or "无法识别的图片格式")
            return
        self.set_image(loaded.image, path)
        self.changed.emit()

    def _adjust(self) -> None:
        if self.original is None:
            return
        dlg = CropDialog(self.original, self.box, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_box is not None:
            self.set_box(dlg.result_box)


class CropCanvas(QWidget):
    """原始照片 + 可拖拽的裁剪框，框的比例锁定为 85.6 : 54。"""

    def __init__(self, image: QImage, parent=None) -> None:
        super().__init__(parent)
        self.image = image
        self.rect_img = QRectF()
        self._k = 1.0
        self._ox = 0.0
        self._oy = 0.0
        self._anchor: Optional[QPointF] = None
        self._dragging = False
        self.setMinimumSize(560, 380)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # ---- 坐标换算
    def _fit(self) -> None:
        pad = 12
        w = max(50, self.width() - 2 * pad)
        h = max(50, self.height() - 2 * pad)
        self._k = min(w / self.image.width(), h / self.image.height())
        self._ox = (self.width() - self.image.width() * self._k) / 2
        self._oy = (self.height() - self.image.height() * self._k) / 2

    def _to_img(self, pos: QPointF) -> QPointF:
        return QPointF((pos.x() - self._ox) / self._k, (pos.y() - self._oy) / self._k)

    def _to_widget(self, r: QRectF) -> QRectF:
        return QRectF(self._ox + r.x() * self._k, self._oy + r.y() * self._k,
                      r.width() * self._k, r.height() * self._k)

    def set_rect(self, r: QRectF) -> None:
        self.rect_img = QRectF(r)
        self.update()

    def set_auto_box(self) -> None:
        box = idcard.detect_card_box(self.image)
        self.set_rect(box.bounds())

    # ---- 绘制
    def paintEvent(self, _e) -> None:
        self._fit()
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#22262e"))
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        target = QRectF(self._ox, self._oy,
                        self.image.width() * self._k, self.image.height() * self._k)
        p.drawImage(target, self.image, QRectF(self.image.rect()))

        r = self._to_widget(self.rect_img)
        # 框外压暗：用 even-odd 填充在整图上挖一个洞，比画四条边稳
        path = QPainterPath()
        path.addRect(QRectF(target))
        path.addRect(r)
        p.setPen(Qt.PenStyle.NoPen)
        p.fillPath(path, QColor(0, 0, 0, 110))

        pen = QPen(QColor("#4c8dff"), 1.6)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)
        p.setBrush(QColor("#ffffff"))
        for pt in (r.topLeft(), r.topRight(), r.bottomLeft(), r.bottomRight()):
            p.drawRect(QRectF(pt.x() - 3, pt.y() - 3, 6, 6))

    # ---- 拖拽
    def mousePressEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton:
            return
        self._anchor = self._to_img(e.position())
        self._dragging = True

    def mouseMoveEvent(self, e) -> None:
        if not self._dragging or self._anchor is None:
            return
        cur = self._to_img(e.position())
        dx = cur.x() - self._anchor.x()
        dy = cur.y() - self._anchor.y()
        w = max(abs(dx), abs(dy) * CARD_RATIO)
        h = w / CARD_RATIO
        x = self._anchor.x() if dx >= 0 else self._anchor.x() - w
        y = self._anchor.y() if dy >= 0 else self._anchor.y() - h
        rect = QRectF(x, y, w, h).intersected(QRectF(self.image.rect()))
        if rect.width() > 8:
            self.rect_img = rect
            self.update()

    def mouseReleaseEvent(self, e) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self._anchor = None
        if self.rect_img.width() < 24 or self.rect_img.height() < 24:
            self.rect_img = QRectF()

    def box(self) -> Optional[CardBox]:
        r = self.rect_img
        if r.width() < 16 or r.height() < 16:
            return None
        return CardBox(r.center().x(), r.center().y(), r.width(), r.height(), 0.0, 1.0)


class CropDialog(QDialog):
    def __init__(self, image: QImage, box: Optional[CardBox], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("调整裁剪范围")
        self.result_box: Optional[CardBox] = None
        self.orig = image
        if max(image.width(), image.height()) > 1400:
            self.image = image.scaled(1400, 1400, Qt.AspectRatioMode.KeepAspectRatio,
                                      Qt.TransformationMode.SmoothTransformation)
        else:
            self.image = image
        self._scale = self.image.width() / max(1, image.width())

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 0)
        root.setSpacing(8)

        tip = QLabel("在照片上按住鼠标左键拖动，框出身份证区域（比例已锁定 85.6 : 54）")
        tip.setObjectName("subtitle")
        root.addWidget(tip)
        self.canvas = CropCanvas(self.image)
        root.addWidget(self.canvas, 1)
        if box is not None:
            b = box.bounds()
            self.canvas.set_rect(QRectF(b.x() * self._scale, b.y() * self._scale,
                                        b.width() * self._scale, b.height() * self._scale))

        footer = QFrame()
        footer.setObjectName("footer")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(0, 10, 0, 10)
        btn_auto = QPushButton("重新自动识别")
        btn_auto.clicked.connect(self._auto)
        fl.addWidget(btn_auto)
        fl.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("确定")
        ok.setObjectName("primary")
        ok.setDefault(True)
        ok.clicked.connect(self._accept)
        fl.addWidget(cancel)
        fl.addWidget(ok)
        root.addWidget(footer)

        self.resize(820, 620)

    def _auto(self) -> None:
        self.canvas.set_auto_box()

    def _accept(self) -> None:
        box = self.canvas.box()
        if box is None:
            QMessageBox.information(self, "还没有框选", "请在照片上拖动，框出身份证区域。")
            return
        k = 1.0 / self._scale
        self.result_box = CardBox(box.cx * k, box.cy * k, box.w * k, box.h * k, 0.0, 1.0)
        self.accept()


class IdCardDialog(QDialog):
    """身份证打印设置。"""

    def __init__(self, front: Optional[QImage] = None, front_path: str = "",
                 back: Optional[QImage] = None, back_path: str = "",
                 options: Optional[IdCardOptions] = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("身份证打印")
        self.opts = IdCardOptions(**(vars(options) if options else {}))
        self._printer0 = printing.make_printer(self.opts.printer_name)
        printing.ensure_a4(self._printer0)
        printing.apply_margins(self._printer0, self.opts.margin_mm)
        printing.apply_duplex(self._printer0, self.opts.duplex)
        self.pdf_path = ""

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._refresh_preview)

        self.setMinimumSize(980, 660)
        self._build_ui()
        if front is not None:
            self.slot_front.set_image(front, front_path)
        if back is not None:
            self.slot_back.set_image(back, back_path)
        QTimer.singleShot(0, self._refresh_preview)

    @property
    def printer(self) -> QPrinter:
        return self.printer_row.printer

    # ------------------------------------------------------------ 界面
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        body = QHBoxLayout()
        body.setContentsMargins(16, 16, 16, 8)
        body.setSpacing(14)

        self.preview = PagePreview()
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(8)
        left.addWidget(self.preview, 1)
        self.page_label = QLabel("A4 · 实际尺寸 85.6 × 54 mm")
        self.page_label.setObjectName("subtitle")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left.addWidget(self.page_label)
        body.addLayout(left, 1)

        side = QVBoxLayout()
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(8)

        self.slot_front = CardSlot("正面 · 人像面", "未选择")
        self.slot_back = CardSlot("反面 · 国徽面", "未选择")
        for slot in (self.slot_front, self.slot_back):
            slot.changed.connect(self._on_change)

        side.addWidget(self._title("身份证正反面"))
        side.addWidget(self.slot_front)
        side.addWidget(self.slot_back)

        # 排列 / 间距 / 边距 / 份数
        self.layout_box = QComboBox()
        self.layout_box.addItem("上下排列", "vertical")
        self.layout_box.addItem("左右排列", "horizontal")
        self.layout_box.setCurrentIndex(max(0, self.layout_box.findData(self.opts.layout)))
        self.layout_box.currentIndexChanged.connect(self._on_change)

        self.gap_spin = QSpinBox()
        self.gap_spin.setRange(0, 120)
        self.gap_spin.setSuffix(" mm")
        self.gap_spin.setValue(int(round(self.opts.gap_mm)))
        self.gap_spin.valueChanged.connect(self._on_change)

        self.margin_spin = QSpinBox()
        self.margin_spin.setRange(0, 40)
        self.margin_spin.setSuffix(" mm")
        self.margin_spin.setValue(int(round(self.opts.margin_mm)))
        self.margin_spin.valueChanged.connect(self._on_change)

        self.copies_spin = QSpinBox()
        self.copies_spin.setRange(1, 20)
        self.copies_spin.setSuffix(" 份")
        self.copies_spin.setValue(max(1, int(self.opts.copies)))
        self.copies_spin.valueChanged.connect(self._on_change)

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(QLabel("排列"))
        row1.addWidget(self.layout_box, 1)
        row1.addWidget(QLabel("间距"))
        row1.addWidget(self.gap_spin)
        side.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(QLabel("页边距"))
        row2.addWidget(self.margin_spin)
        row2.addWidget(QLabel("份数"))
        row2.addWidget(self.copies_spin)
        row2.addStretch(1)
        side.addLayout(row2)

        self.cb_border = QCheckBox("给卡片加细边框（便于裁切）")
        self.cb_border.setChecked(self.opts.border)
        self.cb_border.toggled.connect(self._on_change)
        side.addWidget(self.cb_border)

        side.addSpacing(2)
        self.printer_row = PrinterRow(self._printer0, self)
        self.printer_row.set_duplex(self.opts.duplex)
        self.printer_row.changed.connect(self._on_printer_changed)
        side.addWidget(self.printer_row)

        self.btn_pdf = QPushButton("导出为 PDF…")
        self.btn_pdf.clicked.connect(self._export_pdf)
        side.addWidget(self.btn_pdf)
        side.addStretch(1)
        body.addLayout(side, 0)

        wrap = QWidget()
        wrap.setLayout(body)
        root.addWidget(wrap, 1)

        footer = QFrame()
        footer.setObjectName("footer")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 10, 16, 10)
        self.lb_info = QLabel("")
        self.lb_info.setObjectName("subtitle")
        fl.addWidget(self.lb_info)
        fl.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        self.btn_print = QPushButton("打印")
        self.btn_print.setObjectName("primary")
        self.btn_print.setDefault(True)
        self.btn_print.clicked.connect(self._do_print)
        fl.addWidget(cancel)
        fl.addWidget(self.btn_print)
        root.addWidget(footer)

    @staticmethod
    def _title(text: str) -> QLabel:
        lb = QLabel(text)
        lb.setStyleSheet("font-weight:600;font-size:14px;")
        return lb

    # ------------------------------------------------------------ 状态
    def _sync_options(self) -> None:
        self.opts.layout = str(self.layout_box.currentData() or "vertical")
        self.opts.gap_mm = float(self.gap_spin.value())
        self.opts.margin_mm = float(self.margin_spin.value())
        self.opts.copies = int(self.copies_spin.value())
        self.opts.border = self.cb_border.isChecked()
        self.opts.duplex = self.printer_row.duplex_key()
        self.opts.printer_name = self.printer.printerName()

    def _on_change(self, *_a) -> None:
        self._sync_options()
        self._timer.start()

    def _on_printer_changed(self) -> None:
        printing.apply_margins(self.printer, self.opts.margin_mm)
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        self._sync_options()
        front = self.slot_front.crop()
        back = self.slot_back.crop()
        if front is None and back is None:
            self.preview.set_page(None, "先选择正面和反面的照片")
            self.btn_print.setEnabled(False)
            self.lb_info.setText("尚未选择图片")
            return
        self.btn_print.setEnabled(True)
        printing.apply_margins(self.printer, self.opts.margin_mm)
        try:
            img = idcard.preview(self.printer, front, back, self.opts, (700, 840))
        except Exception as exc:                           # noqa: BLE001
            self.preview.set_page(None, f"预览失败：{exc}")
            return
        self.preview.set_page(img)
        pw, ph = printing.paper_mm(self.printer)
        n = max(1, int(self.opts.copies))
        self.page_label.setText(f"A4 · 实际尺寸 {CARD_W_MM} × {CARD_H_MM} mm · "
                                f"共 {n} 页")
        sides = "正反面" if (front is not None and back is not None) else "单面"
        self.lb_info.setText(f"{self.printer.printerName() or '无打印机'} · {pw:.0f}×{ph:.0f} mm · "
                             f"{sides}")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._refresh_preview()

    # ------------------------------------------------------------ 动作
    def _export_pdf(self) -> None:
        self._sync_options()
        suggest = "身份证.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "导出为 PDF", suggest, "PDF 文件 (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            out = QPrinter(QPrinter.PrinterMode.HighResolution)
            out.setPageLayout(self.printer.pageLayout())
            n = idcard.export_pdf(out, path, self.slot_front.crop(),
                                  self.slot_back.crop(), self.opts)
        except Exception as exc:                           # noqa: BLE001
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        QApplication.restoreOverrideCursor()
        if not os.path.exists(path):
            QMessageBox.warning(self, "导出失败", "PDF 没有生成，请检查目标路径是否可写。")
            return
        self.pdf_path = path
        size = os.path.getsize(path) / 1024
        ret = QMessageBox.question(
            self, "已导出", f"已生成 PDF（{n} 页，{size:.0f} KB）：\n{path}\n\n是否用系统默认程序打开？")
        if ret == QMessageBox.StandardButton.Yes:
            try:
                os.startfile(path)                         # noqa: S606
            except Exception:
                pass

    def _do_print(self) -> None:
        self._sync_options()
        if self.slot_front.crop() is None and self.slot_back.crop() is None:
            QMessageBox.information(self, "打印", "请先选择身份证正面或反面的照片。")
            return
        self.accept()

    # ------------------------------------------------------------ 结果
    @property
    def front(self) -> Optional[QImage]:
        return self.slot_front.crop()

    @property
    def back(self) -> Optional[QImage]:
        return self.slot_back.crop()
