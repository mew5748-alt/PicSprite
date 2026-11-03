# -*- coding: utf-8 -*-
"""单图相关对话框：另存为、压缩到指定大小、调整尺寸、添加文字、属性、快捷键速查。"""
from __future__ import annotations

import os
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QFontMetrics, QImage,
                           QKeySequence)
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox,
                               QDialog, QDialogButtonBox, QFileDialog,
                               QFontComboBox, QFormLayout, QGridLayout, QGroupBox,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QSlider,
                               QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from . import imageio, util
from .config import ACTION_MAP, ACTIONS, settings
from .workers import EncodeTask, TaskPool

SIZE_MODES = [
    ("percent", "按百分比缩放"),
    ("long_edge", "限制长边"),
    ("width", "指定宽度"),
    ("height", "指定高度"),
    ("exact", "精确宽高"),
]


class ColorButton(QPushButton):
    def __init__(self, color: QColor = QColor("#e53935"), parent=None) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(66, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._pick)
        self._refresh()

    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, c) -> None:
        self._color = QColor(c)
        self._refresh()

    def _refresh(self) -> None:
        border = "#c5cad3" if self._color.lightness() > 235 else self._color.darker(120).name()
        self.setStyleSheet(
            f"QPushButton{{background:{self._color.name()};border:1px solid {border};"
            f"border-radius:6px;}} QPushButton:hover{{border:1px solid #2f6fed;}}")
        self.setToolTip(f"颜色 {self._color.name().upper()}")

    def _pick(self) -> None:
        c = QColorDialog.getColor(self._color, self, "选择颜色")
        if c.isValid():
            self.set_color(c)


# --------------------------------------------------------------------- 另存为

class SaveAsDialog(QDialog):
    """格式转换 / 调整尺寸 / 限制体积，三件事一个窗口搞定。"""

    def __init__(self, src_path: str, qimage: QImage,
                 exif_bytes: Optional[bytes] = None, icc: Optional[bytes] = None,
                 default_fmt: str = "JPEG", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("另存为")
        self.setMinimumWidth(600)
        self._qimage = qimage
        self._exif_bytes = exif_bytes
        self._icc = icc
        self._src_path = src_path
        self._pool = TaskPool(2)
        self._estimate_task = None
        self.params: dict = {}

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(320)
        self._timer.timeout.connect(self._update_estimate)

        self._build(default_fmt)
        self._sync_format()
        self._update_new_size()
        self._timer.start()

    # ---------------- UI
    def _build(self, default_fmt: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        # 文件
        box_file = QGroupBox("保存位置与格式")
        g = QGridLayout(box_file)
        g.setHorizontalSpacing(8)
        g.setVerticalSpacing(8)
        g.addWidget(QLabel("保存到"), 0, 0)
        self.path_edit = QLineEdit(self._default_path(default_fmt))
        self.path_edit.setCursorPosition(0)
        self.path_edit.textChanged.connect(lambda _t: self._timer.start())
        g.addWidget(self.path_edit, 0, 1, 1, 2)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse)
        g.addWidget(browse, 0, 3)

        g.addWidget(QLabel("格式"), 1, 0)
        self.fmt_box = QComboBox()
        for spec in imageio.WRITE_FORMATS:
            self.fmt_box.addItem(spec.label, spec.key)
        idx = max(0, self.fmt_box.findData(default_fmt))
        self.fmt_box.setCurrentIndex(idx)
        self.fmt_box.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.fmt_box.setMinimumContentsLength(16)
        self.fmt_box.currentIndexChanged.connect(self._on_fmt_changed)
        g.addWidget(self.fmt_box, 1, 1, 1, 2)

        g.addWidget(QLabel("质量"), 2, 0)
        qrow = QHBoxLayout()
        self.quality = QSlider(Qt.Orientation.Horizontal)
        self.quality.setRange(10, 100)
        self.quality.setValue(88)
        self.quality.valueChanged.connect(self._on_quality)
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(10, 100)
        self.quality_spin.setValue(88)
        self.quality_spin.setFixedWidth(62)
        self.quality_spin.valueChanged.connect(self.quality.setValue)
        self.quality.valueChanged.connect(self.quality_spin.setValue)
        qrow.addWidget(self.quality, 1)
        qrow.addWidget(self.quality_spin)
        g.addLayout(qrow, 2, 1, 1, 3)
        root.addWidget(box_file)

        # 尺寸
        box_size = QGroupBox("图像尺寸")
        s = QGridLayout(box_size)
        s.setHorizontalSpacing(8)
        s.setVerticalSpacing(8)
        self.resize_check = QCheckBox("调整尺寸")
        self.resize_check.toggled.connect(self._on_resize_toggle)
        s.addWidget(self.resize_check, 0, 0, 1, 4)

        s.addWidget(QLabel("方式"), 1, 0)
        self.size_mode = QComboBox()
        for key, label in SIZE_MODES:
            self.size_mode.addItem(label, key)
        self.size_mode.setCurrentIndex(1)
        self.size_mode.currentIndexChanged.connect(self._update_new_size)
        s.addWidget(self.size_mode, 1, 1, 1, 3)

        s.addWidget(QLabel("数值"), 2, 0)
        val_row = QHBoxLayout()
        self.val1 = QSpinBox()
        self.val1.setRange(1, 100000)
        self.val1.setValue(max(1, self._qimage.width()))
        self.val2 = QSpinBox()
        self.val2.setRange(1, 100000)
        self.val2.setValue(max(1, self._qimage.height()))
        self.unit1 = QLabel("像素")
        self.unit2 = QLabel("像素")
        self.keep_ratio = QCheckBox("保持比例")
        self.keep_ratio.setChecked(True)
        for w in (self.val1, self.unit1, QLabel("×"), self.val2, self.unit2):
            val_row.addWidget(w)
        val_row.addWidget(self.keep_ratio)
        val_row.addStretch(1)
        self.val1.valueChanged.connect(self._update_new_size)
        self.val2.valueChanged.connect(self._update_new_size)
        self.keep_ratio.toggled.connect(self._update_new_size)
        s.addLayout(val_row, 2, 1, 1, 3)

        self.new_size_label = QLabel("")
        self.new_size_label.setObjectName("subtitle")
        s.addWidget(self.new_size_label, 3, 0, 1, 4)
        root.addWidget(box_size)

        # 体积
        box_budget = QGroupBox("文件体积")
        b = QHBoxLayout(box_budget)
        self.budget_check = QCheckBox("压缩到不超过")
        self.budget_check.toggled.connect(self._on_budget_toggle)
        b.addWidget(self.budget_check)
        self.budget_spin = QSpinBox()
        self.budget_spin.setRange(5, 200000)
        self.budget_spin.setValue(500)
        self.budget_spin.setFixedWidth(90)
        self.budget_spin.valueChanged.connect(lambda _v: self._timer.start())
        b.addWidget(self.budget_spin)
        self.budget_unit = QComboBox()
        self.budget_unit.addItem("KB", 1024)
        self.budget_unit.addItem("MB", 1024 * 1024)
        self.budget_unit.currentIndexChanged.connect(lambda _i: self._timer.start())
        b.addWidget(self.budget_unit)
        self.budget_hint = QLabel("开启后会优先降低质量，必要时缩小尺寸")
        self.budget_hint.setObjectName("subtitle")
        b.addWidget(self.budget_hint, 1)
        root.addWidget(box_budget)

        # 底部
        bottom = QHBoxLayout()
        self.exif_check = QCheckBox("保留 EXIF 信息")
        self.exif_check.setChecked(True)
        self.exif_check.setEnabled(bool(self._exif_bytes))
        self.exif_check.toggled.connect(lambda _v: self._timer.start())
        bottom.addWidget(self.exif_check)
        bottom.addStretch(1)
        self.estimate_label = QLabel("预计大小：计算中…")
        self.estimate_label.setObjectName("subtitle")
        bottom.addWidget(self.estimate_label)
        root.addLayout(bottom)

        btns = QDialogButtonBox()
        ok = btns.addButton("保存", QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setDefault(True)
        cancel = btns.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self._on_resize_toggle(False)

    def _default_path(self, fmt: str) -> str:
        spec = imageio.FORMAT_BY_KEY.get(fmt, imageio.FORMAT_BY_KEY["JPEG"])
        folder = os.path.dirname(self._src_path) or os.getcwd()
        stem = os.path.splitext(os.path.basename(self._src_path))[0] if self._src_path else "未命名"
        cur_ext = os.path.splitext(self._src_path)[1].lower() if self._src_path else ""
        if cur_ext == spec.ext:
            return os.path.join(folder, f"{stem}_副本{spec.ext}")
        return os.path.join(folder, f"{stem}{spec.ext}")

    # ---------------- 交互
    def _browse(self) -> None:
        spec = imageio.FORMAT_BY_KEY[self.fmt_box.currentData()]
        filt = f"{spec.label.split('·')[0].strip()} (*{spec.ext});;所有文件 (*.*)"
        path, _ = QFileDialog.getSaveFileName(self, "保存为", self.path_edit.text(), filt)
        if path:
            self.path_edit.setText(path)

    def _on_fmt_changed(self) -> None:
        self._sync_format()

    def _sync_format(self) -> None:
        spec = imageio.FORMAT_BY_KEY[self.fmt_box.currentData()]
        self.quality.setEnabled(spec.quality)
        self.quality_spin.setEnabled(spec.quality)
        # 同步扩展名
        cur = self.path_edit.text().strip()
        if cur:
            base, _ext = os.path.splitext(cur)
            self.path_edit.setText(base + spec.ext)
            self.path_edit.setCursorPosition(0)
        self.budget_hint.setVisible(not spec.quality)
        if not spec.quality:
            self.budget_hint.setText("该格式不支持质量参数，将通过缩小尺寸/减少颜色来达标")
        self._timer.start()

    def _on_quality(self, v: int) -> None:
        if not self.budget_check.isChecked():
            self._timer.start()

    def _on_resize_toggle(self, on: bool) -> None:
        for w in (self.size_mode, self.val1, self.val2, self.unit1, self.unit2, self.keep_ratio):
            w.setEnabled(on)
        self._update_new_size()
        self._timer.start()

    def _on_budget_toggle(self, on: bool) -> None:
        self.quality.setEnabled(not on and imageio.FORMAT_BY_KEY[self.fmt_box.currentData()].quality)
        self.quality_spin.setEnabled(self.quality.isEnabled())
        self._timer.start()

    def _target_dims(self) -> tuple:
        if not self.resize_check.isChecked():
            return (self._qimage.width(), self._qimage.height())
        return imageio.fit_dimensions(
            self._qimage.width(), self._qimage.height(),
            self.size_mode.currentData(), self.val1.value(), self.val2.value(),
            self.keep_ratio.isChecked())

    def _update_new_size(self) -> None:
        w, h = self._target_dims()
        ow, oh = self._qimage.width(), self._qimage.height()
        arrow = "→" if (w, h) != (ow, oh) else "·"
        self.new_size_label.setText(f"原始 {ow} × {oh}　{arrow}　输出 {w} × {h}")
        self._timer.start()

    # ---------------- 预估
    def _budget_bytes(self) -> int:
        if not self.budget_check.isChecked():
            return 0
        return int(self.budget_spin.value() * self.budget_unit.currentData())

    def _render_image(self) -> QImage:
        w, h = self._target_dims()
        if (w, h) == (self._qimage.width(), self._qimage.height()):
            return self._qimage
        return imageio.resize_qimage(self._qimage, w, h)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._timer.start()          # 首次显示时补一次预估

    def _update_estimate(self) -> None:
        img = self._render_image()
        fmt = self.fmt_box.currentData()
        quality = self.quality.value()
        target = self._budget_bytes() or 0
        self.estimate_label.setText("预计大小：计算中…")
        task = EncodeTask(img, fmt, quality, self.exif_check.isChecked(), self._exif_bytes)
        task.signals.result.connect(lambda n: self._on_estimate(n, target, img))
        self._pool.start(task)

    def _on_estimate(self, n: int, target: int, img: QImage) -> None:
        if not n:
            self.estimate_label.setText("预计大小：—")
            return
        txt = f"预计大小：约 {util.human_size(n)}"
        if target and n > target:
            txt += "　（保存时将自动压缩到达标）"
        self.estimate_label.setText(txt)

    # ---------------- 结果
    def accept(self) -> None:
        path = self.path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "提示", "请填写保存路径")
            return
        if not os.path.splitext(path)[1]:
            spec = imageio.FORMAT_BY_KEY[self.fmt_box.currentData()]
            path += spec.ext
            self.path_edit.setText(path)
        folder = os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(folder):
            QMessageBox.warning(self, "提示", "目标文件夹不存在")
            return
        if os.path.exists(path):
            same = os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(self._src_path))
            msg = "该文件已存在，确定覆盖吗？" if same else "目标文件已存在，确定覆盖吗？"
            if QMessageBox.question(self, "确认覆盖", msg) != QMessageBox.StandardButton.Yes:
                return
        self.params = {
            "path": path,
            "fmt": self.fmt_box.currentData(),
            "quality": self.quality.value(),
            "resize": self._target_dims() if self.resize_check.isChecked() else None,
            "target_bytes": self._budget_bytes(),
            "keep_exif": self.exif_check.isChecked(),
        }
        super().accept()


# --------------------------------------------------------------------- 压缩到指定大小

class CompressDialog(QDialog):
    def __init__(self, src_path: str, qimage: QImage,
                 exif_bytes: Optional[bytes] = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("压缩到指定大小")
        self.setMinimumWidth(480)
        self._src = src_path
        self._qimage = qimage
        self._exif = exif_bytes
        self.saved_path = ""
        self.result_info = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        try:
            orig = os.path.getsize(src_path)
        except OSError:
            orig = 0
        info = QLabel(f"当前文件：{os.path.basename(src_path)}　"
                      f"{imageio.format_label(src_path)}　"
                      f"{qimage.width()} × {qimage.height()}　{util.human_size(orig)}")
        info.setObjectName("subtitle")
        info.setWordWrap(True)
        root.addWidget(info)

        box = QGroupBox("目标")
        f = QFormLayout(box)
        f.setSpacing(8)
        target_row = QHBoxLayout()
        self.size_spin = QSpinBox()
        self.size_spin.setRange(3, 200000)
        self.size_spin.setValue(max(20, int(orig / 1024 * 0.5)) if orig else 200)
        target_row.addWidget(self.size_spin)
        self.unit = QComboBox()
        self.unit.addItem("KB", 1024)
        self.unit.addItem("MB", 1024 * 1024)
        target_row.addWidget(self.unit)
        target_row.addStretch(1)
        f.addRow("压缩到不超过", target_row)

        self.fmt_box = QComboBox()
        self.fmt_box.addItem("JPG / JPEG（推荐，照片效果最好）", "JPEG")
        self.fmt_box.addItem("WebP（同画质更小）", "WEBP")
        self.fmt_box.addItem("保持原格式", "KEEP")
        f.addRow("输出格式", self.fmt_box)

        self.allow_resize = QCheckBox("必要时缩小图片尺寸（更容易达标）")
        self.allow_resize.setChecked(True)
        f.addRow("", self.allow_resize)

        out_row = QVBoxLayout()
        self.radio_suffix = QCheckBox("保存到同目录，文件名加“_压缩”后缀")
        self.radio_suffix.setChecked(True)
        self.radio_over = QCheckBox("直接覆盖原文件（会先备份）")
        out_row.addWidget(self.radio_suffix)
        out_row.addWidget(self.radio_over)
        f.addRow("输出", out_row)
        root.addWidget(box)

        self.hint = QLabel("提示：JPG 通过降低质量来减小体积；若目标过小，会自动缩小尺寸。")
        self.hint.setObjectName("subtitle")
        self.hint.setWordWrap(True)
        root.addWidget(self.hint)

        btns = QDialogButtonBox()
        ok = btns.addButton("开始压缩", QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setDefault(True)
        btns.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        btns.accepted.connect(self._run)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _fmt(self) -> str:
        key = self.fmt_box.currentData()
        if key == "KEEP":
            f = imageio.load_image(self._src, max_frames=1).fmt
            return f if f in imageio.FORMAT_BY_KEY else "JPEG"
        return key

    def _run(self) -> None:
        target = int(self.size_spin.value() * self.unit.currentData())
        fmt = self._fmt()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            res = imageio.compress_to_target(self._qimage, fmt, target,
                                             self.allow_resize.isChecked(),
                                             True, self._exif)
            if self.radio_over.isChecked():
                out = self._src
            else:
                stem, ext = os.path.splitext(self._src)
                new_ext = imageio.FORMAT_BY_KEY[fmt].ext
                out = util.unique_path(f"{stem}_压缩{new_ext}")
            from .config import backup_dir
            if os.path.exists(out):
                try:
                    import shutil
                    bdir = backup_dir(os.path.dirname(os.path.abspath(out)))
                    shutil.copy2(out, os.path.join(bdir, os.path.basename(out)))
                except Exception:
                    pass
            imageio.write_bytes_atomic(out, res.data)
        except Exception as e:                        # noqa: BLE001
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "压缩失败", str(e))
            return
        QApplication.restoreOverrideCursor()

        self.saved_path = out
        flag = "已达标" if res.reached else "已尽可能压缩（未完全达标）"
        self.result_info = (f"{flag}\n\n输出文件：{out}\n"
                            f"体积：{util.human_size(res.size)}\n"
                            f"尺寸：{res.width} × {res.height}\n"
                            f"质量参数：{res.quality}")
        QMessageBox.information(self, "压缩完成", self.result_info)
        super().accept()


# --------------------------------------------------------------------- 调整尺寸

class ResizeDialog(QDialog):
    def __init__(self, width: int, height: int, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("调整尺寸")
        self.setMinimumWidth(420)
        self._w, self._h = width, height
        self.result_size = (width, height)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        cur = QLabel(f"当前尺寸：{width} × {height} 像素")
        cur.setObjectName("subtitle")
        root.addWidget(cur)

        box = QGroupBox("新尺寸")
        f = QFormLayout(box)
        f.setSpacing(8)
        self.mode = QComboBox()
        for key, label in SIZE_MODES:
            self.mode.addItem(label, key)
        self.mode.setCurrentIndex(1)
        f.addRow("方式", self.mode)

        row = QHBoxLayout()
        self.val1 = QSpinBox()
        self.val1.setRange(1, 100000)
        self.val1.setValue(max(width, height))
        self.val2 = QSpinBox()
        self.val2.setRange(1, 100000)
        self.val2.setValue(height)
        self.lbl1 = QLabel("像素")
        self.lbl2 = QLabel("×")
        row.addWidget(self.val1)
        row.addWidget(self.lbl1)
        row.addWidget(self.lbl2)
        row.addWidget(self.val2)
        row.addStretch(1)
        f.addRow("数值", row)

        self.keep = QCheckBox("保持宽高比例")
        self.keep.setChecked(True)
        f.addRow("", self.keep)
        root.addWidget(box)

        self.preview = QLabel("")
        root.addWidget(self.preview)

        btns = QDialogButtonBox()
        ok = btns.addButton("确定", QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setDefault(True)
        btns.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self.mode.currentIndexChanged.connect(self._sync)
        self.val1.valueChanged.connect(self._update)
        self.val2.valueChanged.connect(self._update)
        self.keep.toggled.connect(self._update)
        self._sync()

    def _sync(self) -> None:
        mode = self.mode.currentData()
        self.val2.setVisible(mode in ("exact",))
        self.lbl2.setVisible(mode in ("exact",))
        self.keep.setVisible(mode in ("exact",))
        if mode == "percent":
            self.lbl1.setText("%")
            self.val1.setValue(100)
            self.val1.setRange(1, 1000)
        else:
            self.lbl1.setText("像素")
            self.val1.setRange(1, 100000)
            if mode == "long_edge":
                self.val1.setValue(max(self._w, self._h))
            elif mode == "width":
                self.val1.setValue(self._w)
            elif mode == "height":
                self.val1.setValue(self._h)
        self._update()

    def _update(self) -> None:
        w, h = imageio.fit_dimensions(
            self._w, self._h, self.mode.currentData(), self.val1.value(),
            self.val2.value(), self.keep.isChecked())
        self.preview.setText(f"输出尺寸：<b>{w} × {h}</b> 像素　"
                             f"（原始 {self._w} × {self._h}）")
        self.result_size = (w, h)

    def accept(self) -> None:
        self._update()
        super().accept()


# --------------------------------------------------------------------- 添加文字

class TextDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("添加文字")
        self.setMinimumWidth(440)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        self.editor = QPlainTextEdit()
        self.editor.setPlaceholderText("输入要添加的文字（支持多行）")
        self.editor.setFixedHeight(84)
        root.addWidget(self.editor)

        box = QGroupBox("文字样式")
        f = QFormLayout(box)
        f.setSpacing(8)

        self.font_box = QFontComboBox()
        self.font_box.setCurrentFont(QFont("Microsoft YaHei"))
        f.addRow("字体", self.font_box)

        row = QHBoxLayout()
        self.size_spin = QSpinBox()
        self.size_spin.setRange(8, 400)
        self.size_spin.setValue(36)
        row.addWidget(self.size_spin)
        self.bold = QCheckBox("加粗")
        self.italic = QCheckBox("倾斜")
        row.addWidget(self.bold)
        row.addWidget(self.italic)
        row.addStretch(1)
        f.addRow("字号", row)

        row2 = QHBoxLayout()
        self.color_btn = ColorButton(QColor("#ff3b30"))
        row2.addWidget(self.color_btn)
        self.outline = QCheckBox("描边（浅色照片上更清楚）")
        self.outline.setChecked(True)
        row2.addWidget(self.outline)
        row2.addStretch(1)
        f.addRow("颜色", row2)
        root.addWidget(box)

        self.preview = QLabel("预览效果")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setFixedHeight(64)
        self.preview.setStyleSheet("background:#ffffff;border:1px solid #e4e7ec;border-radius:8px;")
        root.addWidget(self.preview)

        btns = QDialogButtonBox()
        ok = btns.addButton("放到图片上", QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setDefault(True)
        btns.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        for w in (self.font_box, ):
            w.currentFontChanged.connect(self._refresh)
        self.size_spin.valueChanged.connect(self._refresh)
        self.bold.toggled.connect(self._refresh)
        self.italic.toggled.connect(self._refresh)
        self.outline.toggled.connect(self._refresh)
        self.editor.textChanged.connect(self._refresh)
        self._refresh()

    def _font(self) -> QFont:
        f = QFont(self.font_box.currentFont())
        f.setPointSize(self.size_spin.value())
        f.setBold(self.bold.isChecked())
        f.setItalic(self.italic.isChecked())
        return f

    def _refresh(self) -> None:
        f = self._font()
        c = self.color_btn.color()
        text = self.editor.toPlainText().strip() or "示例文字"
        self.preview.setText(text.split("\n")[0])
        f2 = QFont(f)
        f2.setPointSize(min(f.pointSize(), 22))
        self.preview.setFont(f2)
        self.preview.setStyleSheet(
            "background:#ffffff;border:1px solid #e4e7ec;border-radius:8px;"
            f"color:{c.name()};")

    def values(self) -> dict:
        return {
            "text": self.editor.toPlainText(),
            "font": self._font(),
            "color": self.color_btn.color(),
            "outline": self.outline.isChecked(),
        }

    def accept(self) -> None:
        if not self.editor.toPlainText().strip():
            QMessageBox.warning(self, "提示", "请输入文字内容")
            return
        super().accept()


# --------------------------------------------------------------------- 属性

class PropertiesDialog(QDialog):
    def __init__(self, path: str, loaded, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("图片属性")
        self.setMinimumWidth(460)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        rows = [
            ("文件名", os.path.basename(path)),
            ("所在位置", os.path.dirname(path)),
            ("格式", imageio.format_label(loaded.fmt or path)),
            ("尺寸", f"{loaded.width} × {loaded.height} 像素"),
            ("色彩模式", loaded.mode),
            ("文件大小", f"{util.human_size(loaded.file_size)}（{loaded.file_size:,} 字节）"),
        ]
        try:
            import datetime
            rows.append(("修改时间", datetime.datetime.fromtimestamp(loaded.mtime)
                         .strftime("%Y-%m-%d %H:%M:%S")))
        except Exception:
            pass
        for k, v in loaded.exif.items():
            rows.append((k, v))

        table = QTableWidget(len(rows), 2)
        table.setHorizontalHeaderLabels(["项目", "值"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(0, 96)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for i, (k, v) in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(k))
            table.setItem(i, 1, QTableWidgetItem(str(v)))
        table.resizeRowsToContents()
        root.addWidget(table, 1)

        row = QHBoxLayout()
        btn_copy = QPushButton("复制信息")
        btn_copy.clicked.connect(lambda: self._copy(rows))
        row.addWidget(btn_copy)
        btn_open = QPushButton("打开所在文件夹")
        btn_open.clicked.connect(lambda: util.reveal_in_explorer(path))
        row.addWidget(btn_open)
        row.addStretch(1)
        close = QPushButton("关闭")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        row.addWidget(close)
        root.addLayout(row)

    def _copy(self, rows) -> None:
        text = "\n".join(f"{k}：{v}" for k, v in rows)
        QApplication.clipboard().setText(text)


# --------------------------------------------------------------------- 快捷键速查

class ShortcutsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("快捷键速查")
        self.resize(520, 620)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)

        tip = QLabel("这些快捷键都可以在「设置 → 快捷键」里改成你习惯的按键。")
        tip.setObjectName("subtitle")
        root.addWidget(tip)

        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["功能", "快捷键", "分类"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.setColumnWidth(1, 130)
        table.setColumnWidth(2, 70)

        rows = []
        for a in ACTIONS:
            sc = settings.shortcut(a.id)
            if not sc:
                continue
            rows.append((a.category, a.text, QKeySequence(sc).toString(
                QKeySequence.SequenceFormat.NativeText)))
        rows.sort(key=lambda r: (r[0], r[1]))
        table.setRowCount(len(rows))
        for i, (cat, name, key) in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(name))
            it = QTableWidgetItem(key)
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(i, 1, it)
            table.setItem(i, 2, QTableWidgetItem(cat))
        root.addWidget(table, 1)

        btns = QDialogButtonBox()
        btns.addButton("知道了", QDialogButtonBox.ButtonRole.AcceptRole)
        btns.accepted.connect(self.accept)
        root.addWidget(btns)


def about_text() -> str:
    return (
        "<h3>看图精灵 1.0</h3>"
        "<p>一个为日常使用而生的 Windows 看图工具。</p>"
        "<ul style='margin-left:-8px'>"
        "<li>支持 BMP / JPG / PNG / GIF / TIFF / ICO / WebP 等格式</li>"
        "<li>缩放、旋转、翻转、裁剪、涂鸦、加文字</li>"
        "<li>另存为任意格式，可改尺寸、可压缩到指定体积</li>"
        "<li>批量重命名 / 批量转换 / 批量调整大小</li>"
        "<li>缩略图磁盘缓存，切换文件夹秒开</li>"
        "<li>快捷键与右键菜单都可自定义</li>"
        "</ul>"
        "<p style='color:#7b8290'>基于 PySide6 + Pillow 构建</p>"
    )
