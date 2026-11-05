# -*- coding: utf-8 -*-
"""打印对话框：实时预览 + 排版选项 + 直接导出 PDF。"""
from __future__ import annotations

import os
from typing import Callable, List, Optional, Tuple

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (QColor, QFont, QImage, QPainter, QPageLayout, QPen,
                           QPixmap)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,
                               QDoubleSpinBox, QFileDialog, QFrame, QHBoxLayout,
                               QLabel, QMessageBox, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from . import printing
from .printing import PER_PAGES, SCALES, PrintItem, PrintOptions


class PagePreview(QWidget):
    """把一页预览图居中画出来，底下垫一层纸张阴影。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pm: Optional[QPixmap] = None
        self._hint = "正在准备预览…"
        self.setMinimumSize(300, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_page(self, img: Optional[QImage], hint: str = "") -> None:
        self._pm = QPixmap.fromImage(img) if img is not None and not img.isNull() else None
        self._hint = hint
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.fillRect(self.rect(), QColor("#eef1f6"))

        if self._pm is None:
            p.setPen(QColor("#9aa3b2"))
            f = QFont(printing.FONT_FAMILY)
            f.setPointSize(9)
            p.setFont(f)
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), self._hint)
            return

        avail = self.rect().adjusted(18, 18, -18, -18)
        pm = self._pm
        k = min(avail.width() / pm.width(), avail.height() / pm.height())
        w, h = int(pm.width() * k), int(pm.height() * k)
        x = avail.x() + (avail.width() - w) // 2
        y = avail.y() + (avail.height() - h) // 2

        # 纸张阴影
        for i, alpha in enumerate((18, 12, 8)):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(40, 55, 80, alpha))
            p.drawRoundedRect(QRectF(x - 1 + i, y + 2 + i, w + 2, h + 2), 2, 2)

        p.setBrush(QColor("#ffffff"))
        p.setPen(QPen(QColor("#dde2ea"), 1))
        p.drawRect(QRectF(x - 0.5, y - 0.5, w + 1, h + 1))
        p.drawPixmap(QRectF(x, y, w, h), pm, QRectF(pm.rect()))


class PrintDialog(QDialog):
    """打印设置。

    scopes 是 [(键, 显示文字, 取数据的函数)]，函数返回 List[PrintItem]；
    这样“当前图片 / 选中几张 / 整个文件夹”的取数逻辑留在主窗口，对话框只负责排版。
    """

    def __init__(self, printer: QPrinter,
                 scopes: List[Tuple[str, str, Callable[[], List[PrintItem]]]],
                 options: PrintOptions, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("打印")
        self.printer = printer
        self._scopes = scopes
        self._items: List[PrintItem] = []
        self._page = 0
        self._pages = 1
        self.opts = PrintOptions(**vars(options))
        self.pdf_path = ""

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._refresh_preview)

        self.setMinimumSize(880, 620)
        self._build_ui()
        self._load_scope(0)

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

        self.btn_prev = QPushButton("上一页")
        self.btn_prev.clicked.connect(lambda: self._go(-1))
        self.btn_next = QPushButton("下一页")
        self.btn_next.clicked.connect(lambda: self._go(1))
        self.page_label = QLabel("第 1 / 1 页")
        self.page_label.setObjectName("subtitle")

        nav = QHBoxLayout()
        nav.setSpacing(8)
        nav.addStretch(1)
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.page_label)
        nav.addWidget(self.btn_next)
        nav.addStretch(1)
        left.addLayout(nav)

        body.addLayout(left, 1)

        side = QVBoxLayout()
        side.setSpacing(9)
        side.setContentsMargins(0, 0, 0, 0)

        title = QLabel("打印设置")
        title.setStyleSheet("font-weight:600;font-size:14px;")
        side.addWidget(title)

        # 打印内容
        self.scope_box = QComboBox()
        for i, (_k, label, _f) in enumerate(self._scopes):
            self.scope_box.addItem(label, i)
        self.scope_box.currentIndexChanged.connect(self._on_scope)
        self.scope_box.setEnabled(len(self._scopes) > 1)
        side.addWidget(self._label("打印内容"))
        side.addWidget(self.scope_box)

        # 每页张数
        self.per_box = QComboBox()
        for n in PER_PAGES:
            self.per_box.addItem(f"每页 {n} 张", n)
        idx = self.per_box.findData(self.opts.per_page)
        self.per_box.setCurrentIndex(max(0, idx))
        self.per_box.currentIndexChanged.connect(self._on_change)
        side.addWidget(self._label("排版"))
        side.addWidget(self.per_box)

        # 缩放
        self.scale_box = QComboBox()
        for key, text in SCALES:
            self.scale_box.addItem(text, key)
        self.scale_box.setCurrentIndex(max(0, self.scale_box.findData(self.opts.scale)))
        self.scale_box.currentIndexChanged.connect(self._on_change)
        side.addWidget(self.scale_box)

        # 页边距 / 间距
        row = QHBoxLayout()
        row.setSpacing(8)
        self.margin_spin = QDoubleSpinBox()
        self.margin_spin.setRange(0, 40)
        self.margin_spin.setSingleStep(1)
        self.margin_spin.setDecimals(1)
        self.margin_spin.setSuffix(" mm")
        self.margin_spin.setValue(self.opts.margin_mm)
        self.margin_spin.valueChanged.connect(self._on_change)
        self.gap_spin = QDoubleSpinBox()
        self.gap_spin.setRange(0, 30)
        self.gap_spin.setSingleStep(1)
        self.gap_spin.setDecimals(1)
        self.gap_spin.setSuffix(" mm")
        self.gap_spin.setValue(self.opts.gap_mm)
        self.gap_spin.valueChanged.connect(self._on_change)
        row.addWidget(QLabel("页边距"))
        row.addWidget(self.margin_spin, 1)
        row.addWidget(QLabel("间距"))
        row.addWidget(self.gap_spin, 1)
        side.addLayout(row)

        self.cb_title = QCheckBox("显示文件名")
        self.cb_title.setChecked(self.opts.show_title)
        self.cb_title.toggled.connect(self._on_change)
        self.cb_date = QCheckBox("显示拍摄日期")
        self.cb_date.setChecked(self.opts.show_date)
        self.cb_date.toggled.connect(self._on_change)
        side.addWidget(self.cb_title)
        side.addWidget(self.cb_date)

        side.addSpacing(6)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color:#e8ecf3;")
        side.addWidget(line)

        self.info = QLabel("")
        self.info.setObjectName("subtitle")
        self.info.setWordWrap(True)
        side.addWidget(self.info)

        self.btn_setup = QPushButton("打印机设置…")
        self.btn_setup.clicked.connect(self._printer_setup)
        side.addWidget(self.btn_setup)

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
    def _label(text: str) -> QLabel:
        lb = QLabel(text)
        lb.setObjectName("section")
        return lb

    # ------------------------------------------------------------ 数据
    def _load_scope(self, index: int) -> None:
        if not (0 <= index < len(self._scopes)):
            return
        _key, _label, fn = self._scopes[index]
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._items = list(fn() or [])
        except Exception:                                     # noqa: BLE001
            self._items = []
        QApplication.restoreOverrideCursor()
        self._page = 0
        self._recalc_pages()

    def _recalc_pages(self) -> None:
        self._pages = max(1, printing.page_count(len(self._items), self.opts.per_page))
        self._page = max(0, min(self._page, self._pages - 1))
        self.page_label.setText(f"第 {self._page + 1} / {self._pages} 页")
        self.btn_prev.setEnabled(self._pages > 1 and self._page > 0)
        self.btn_next.setEnabled(self._pages > 1 and self._page < self._pages - 1)

    def _sync_options(self) -> None:
        self.opts.per_page = int(self.per_box.currentData() or 1)
        self.opts.scale = str(self.scale_box.currentData() or "fit")
        self.opts.margin_mm = float(self.margin_spin.value())
        self.opts.gap_mm = float(self.gap_spin.value())
        self.opts.show_title = self.cb_title.isChecked()
        self.opts.show_date = self.cb_date.isChecked()

    def _printer_summary(self) -> str:
        pw, ph = printing.paper_mm(self.printer)
        name = self.printer.printerName() or "（未选择打印机）"
        land = "横向" if pw > ph else "纵向"
        return f"{name}\n{pw:.0f} × {ph:.0f} mm · {land} · {self.printer.resolution()} dpi"

    # ------------------------------------------------------------ 预览
    def _on_change(self, *_a) -> None:
        self._sync_options()
        self._recalc_pages()
        self._timer.start()

    def _on_scope(self, index: int) -> None:
        self._load_scope(index)
        self._timer.start()

    def _go(self, delta: int) -> None:
        self._page = max(0, min(self._page + delta, self._pages - 1))
        self._recalc_pages()
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        self._sync_options()
        printing.apply_margins(self.printer, self.opts.margin_mm)
        if not self._items:
            self.preview.set_page(None, "没有可打印的图片")
            self.info.setText(self._printer_summary())
            self.btn_print.setEnabled(False)
            return
        self.btn_print.setEnabled(True)
        try:
            img = printing.preview_image(self.printer, self._items, self.opts,
                                         self._page, (720, 860))
        except Exception as exc:                              # noqa: BLE001
            self.preview.set_page(None, f"预览失败：{exc}")
            return
        self.preview.set_page(img)

        n = len(self._items)
        rows = f"共 {n} 张图片，{self._pages} 页"
        self.info.setText(f"{self._printer_summary()}\n{rows}")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._timer.start()

    # ------------------------------------------------------------ 动作
    def _printer_setup(self) -> None:
        dlg = QPrintDialog(self.printer, self)
        dlg.setWindowTitle("打印机设置")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            printing.apply_margins(self.printer, self.opts.margin_mm)
            self._refresh_preview()

    def _export_pdf(self) -> None:
        self._sync_options()
        base = self._items[0].title if self._items else "打印"
        suggest = os.path.splitext(base)[0] + ".pdf"
        path, _ = QFileDialog.getSaveFileName(self, "导出为 PDF", suggest, "PDF 文件 (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            # 用一个独立的 printer 导出，避免把界面上选好的打印机改成 PDF 输出
            out = QPrinter(QPrinter.PrinterMode.HighResolution)
            out.setPageLayout(self.printer.pageLayout())
            n = printing.export_pdf(out, path, self._items, self.opts)
        except Exception as exc:                              # noqa: BLE001
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
            self, "已导出",
            f"已生成 PDF（{n} 页，{size:.0f} KB）：\n{path}\n\n是否用系统默认程序打开？")
        if ret == QMessageBox.StandardButton.Yes:
            try:
                os.startfile(path)                            # noqa: S606
            except Exception:
                pass

    def _do_print(self) -> None:
        self._sync_options()
        if not self._items:
            QMessageBox.information(self, "打印", "没有可打印的图片。")
            return
        self.accept()

    # ------------------------------------------------------------ 结果
    @property
    def items(self) -> List[PrintItem]:
        return self._items
