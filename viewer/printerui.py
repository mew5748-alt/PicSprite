# -*- coding: utf-8 -*-
"""打印机选择 + 单/双面设置，打印对话框和身份证对话框共用。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (QComboBox, QDialog, QGridLayout, QLabel,
                               QPushButton, QWidget)

from . import printing


class PrinterRow(QWidget):
    """一行「打印机 + 设置」，一行「双面」。"""

    changed = Signal()

    def __init__(self, printer: QPrinter, parent=None) -> None:
        super().__init__(parent)
        self._printer = printer
        self._syncing = False

        self.box = QComboBox()
        self.box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.box.setMinimumContentsLength(12)
        for info in printing.available_printers():
            self.box.addItem(info.printerName(), info.printerName())
        if self.box.count() == 0:
            self.box.addItem("（没有可用的打印机）", "")
        self._select_printer(printer.printerName())
        self.box.currentIndexChanged.connect(self._on_printer)

        self.btn_setup = QPushButton("设置…")
        self.btn_setup.setToolTip("纸张、方向、打印质量等由打印机驱动决定")
        self.btn_setup.clicked.connect(self._setup)

        self.duplex = QComboBox()
        for key, text in printing.DUPLEX_MODES:
            self.duplex.addItem(text, key)
        self.duplex.currentIndexChanged.connect(self._on_duplex)
        self.sync_duplex(printer)

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        grid.addWidget(QLabel("打印机"), 0, 0)
        grid.addWidget(self.box, 0, 1)
        grid.addWidget(self.btn_setup, 0, 2)
        grid.addWidget(QLabel("双面"), 1, 0)
        grid.addWidget(self.duplex, 1, 1, 1, 2)
        grid.setColumnStretch(1, 1)

    # ------------------------------------------------------------ 状态
    @property
    def printer(self) -> QPrinter:
        return self._printer

    def duplex_key(self) -> str:
        return str(self.duplex.currentData() or "none")

    def printer_name(self) -> str:
        return str(self.box.currentData() or "")

    def _select_printer(self, name: str) -> None:
        idx = self.box.findData(name)
        if idx < 0:
            idx = 0
        self._syncing = True
        self.box.setCurrentIndex(idx)
        self._syncing = False

    def set_duplex(self, key: str) -> None:
        """按配置恢复上次选的单/双面（不改的话驱动默认可能是双面）。"""
        idx = self.duplex.findData(key)
        if idx >= 0:
            self._syncing = True
            self.duplex.setCurrentIndex(idx)
            self._syncing = False
        printing.apply_duplex(self._printer, key)

    def sync_duplex(self, printer: QPrinter) -> None:
        mode = printer.duplex()
        key = "none"
        if mode == QPrinter.DuplexMode.DuplexLongSide:
            key = "long"
        elif mode == QPrinter.DuplexMode.DuplexShortSide:
            key = "short"
        self._syncing = True
        idx = self.duplex.findData(key)
        self.duplex.setCurrentIndex(max(0, idx))
        self._syncing = False

    # ------------------------------------------------------------ 交互
    def _on_printer(self, _idx: int) -> None:
        if self._syncing:
            return
        layout = self._printer.pageLayout()
        name = self.printer_name()
        new = printing.make_printer(name, layout)
        if not new.isValid():
            new = printing.make_printer(name)
        self._printer = new
        printing.apply_duplex(self._printer, self.duplex_key())
        self.sync_duplex(self._printer)
        self.changed.emit()

    def _on_duplex(self, _idx: int) -> None:
        if self._syncing:
            return
        printing.apply_duplex(self._printer, self.duplex_key())
        self.changed.emit()

    def _setup(self) -> None:
        dlg = QPrintDialog(self._printer, self)
        dlg.setWindowTitle("打印机设置")
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._select_printer(self._printer.printerName())
            self.sync_duplex(self._printer)
            self.changed.emit()
