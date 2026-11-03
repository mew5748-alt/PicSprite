# -*- coding: utf-8 -*-
"""批量处理对话框：重命名 / 转换格式 / 调整尺寸 / 限制体积 / 输出位置。"""
from __future__ import annotations

import os
from typing import List

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QProgressBar,
                               QPushButton, QRadioButton, QSlider, QSpinBox,
                               QTabWidget, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget, QGridLayout)

from . import imageio, util
from .batch import BatchOptions, build_plan
from .config import settings
from .workers import BatchTask, Signals

TOKENS = [
    ("{name}", "原文件名"), ("{n}", "序号"), ("{nn}", "补零序号"),
    ("{date}", "修改日期"), ("{time}", "时间"), ("{parent}", "上级目录"),
    ("{w}", "宽度"), ("{h}", "高度"),
]

CASE_MODES = [("keep", "保持原样"), ("lower", "全部小写"), ("upper", "全部大写"),
              ("title", "首字母大写")]


class BatchDialog(QDialog):
    finished = Signal()

    def __init__(self, paths: List[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("批量处理")
        self.resize(790, 730)
        self.paths = list(paths)
        self._task = None
        self._running = False

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(220)
        self._timer.timeout.connect(self._refresh_preview)

        self._build()
        self._refresh_preview()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        head = QLabel(f"共 <b>{len(self.paths)}</b> 个文件待处理")
        head.setObjectName("title")
        root.addWidget(head)
        folder = os.path.dirname(self.paths[0]) if self.paths else ""
        sub = QLabel(folder if folder else "未选择文件")
        sub.setObjectName("subtitle")
        root.addWidget(sub)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._tab_rename(), "重命名")
        self.tabs.addTab(self._tab_format(), "格式转换")
        self.tabs.addTab(self._tab_size(), "尺寸与体积")
        self.tabs.addTab(self._tab_output(), "输出位置")
        root.addWidget(self.tabs, 0)

        box = QGroupBox("预览")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(8, 8, 8, 8)
        self.table = QTableWidget(0, 4)
        self.table.setMinimumHeight(170)
        self.table.setHorizontalHeaderLabels(["原文件名", "处理后文件名", "操作", "状态"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        from PySide6.QtWidgets import QHeaderView
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(3, 120)
        bl.addWidget(self.table)
        self.preview_note = QLabel("")
        self.preview_note.setObjectName("subtitle")
        bl.addWidget(self.preview_note)
        root.addWidget(box, 1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        root.addWidget(self.progress)

        row = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("subtitle")
        row.addWidget(self.status, 1)
        self.btn_stop = QPushButton("停止")
        self.btn_stop.setVisible(False)
        self.btn_stop.clicked.connect(self._stop)
        row.addWidget(self.btn_stop)

        btns = QDialogButtonBox()
        self.btn_start = btns.addButton("开始处理", QDialogButtonBox.ButtonRole.AcceptRole)
        self.btn_start.setDefault(True)
        self.btn_start.clicked.connect(self._start)
        self.btn_close = btns.addButton("关闭", QDialogButtonBox.ButtonRole.RejectRole)
        self.btn_close.clicked.connect(self.reject)
        row.addWidget(btns)
        root.addLayout(row)

    def _tab_rename(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)

        self.rename_check = QCheckBox("启用批量重命名")
        self.rename_check.setChecked(True)
        self.rename_check.toggled.connect(lambda _v: self._timer.start())
        v.addWidget(self.rename_check)

        form = QFormLayout()
        form.setSpacing(8)
        self.pattern = QLineEdit("{name}")
        self.pattern.setPlaceholderText("例如：旅行_{nn}")
        self.pattern.textChanged.connect(lambda _t: self._timer.start())
        form.addRow("命名规则", self.pattern)

        tok_row = QHBoxLayout()
        tok_row.setSpacing(4)
        for token, tip in TOKENS:
            b = QPushButton(token)
            b.setToolTip(tip)
            b.setFixedHeight(24)
            b.setStyleSheet("QPushButton{padding:2px 7px;font-size:12px;}")
            b.clicked.connect(lambda _c=False, t=token: self._insert_token(t))
            tok_row.addWidget(b)
        tok_row.addStretch(1)
        form.addRow("插入变量", tok_row)

        idx_row = QHBoxLayout()
        self.start_index = QSpinBox()
        self.start_index.setRange(0, 999999)
        self.start_index.setValue(1)
        self.start_index.valueChanged.connect(lambda _v: self._timer.start())
        self.padding = QSpinBox()
        self.padding.setRange(1, 8)
        self.padding.setValue(3)
        self.padding.valueChanged.connect(lambda _v: self._timer.start())
        idx_row.addWidget(QLabel("起始序号"))
        idx_row.addWidget(self.start_index)
        idx_row.addWidget(QLabel("位数"))
        idx_row.addWidget(self.padding)
        idx_row.addStretch(1)
        form.addRow("序号", idx_row)

        fr_row = QHBoxLayout()
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("查找")
        self.replace_edit = QLineEdit()
        self.replace_edit.setPlaceholderText("替换为")
        self.find_edit.textChanged.connect(lambda _t: self._timer.start())
        self.replace_edit.textChanged.connect(lambda _t: self._timer.start())
        fr_row.addWidget(self.find_edit)
        fr_row.addWidget(QLabel("→"))
        fr_row.addWidget(self.replace_edit)
        form.addRow("查找替换", fr_row)

        self.case_box = QComboBox()
        for key, label in CASE_MODES:
            self.case_box.addItem(label, key)
        self.case_box.currentIndexChanged.connect(lambda _i: self._timer.start())
        form.addRow("英文大小写", self.case_box)
        v.addLayout(form)

        self.example = QLabel("")
        self.example.setObjectName("subtitle")
        v.addWidget(self.example)
        v.addStretch(1)
        return w

    def _tab_format(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)

        self.convert_check = QCheckBox("转换为指定格式")
        self.convert_check.toggled.connect(lambda _v: self._timer.start())
        v.addWidget(self.convert_check)

        form = QFormLayout()
        form.setSpacing(8)
        self.fmt_box = QComboBox()
        for spec in imageio.WRITE_FORMATS:
            self.fmt_box.addItem(spec.label, spec.key)
        self.fmt_box.currentIndexChanged.connect(lambda _i: self._timer.start())
        form.addRow("目标格式", self.fmt_box)

        qrow = QHBoxLayout()
        self.quality = QSlider(Qt.Orientation.Horizontal)
        self.quality.setRange(10, 100)
        self.quality.setValue(88)
        self.q_spin = QSpinBox()
        self.q_spin.setRange(10, 100)
        self.q_spin.setValue(88)
        self.q_spin.setFixedWidth(60)
        self.quality.valueChanged.connect(self.q_spin.setValue)
        self.q_spin.valueChanged.connect(self.quality.setValue)
        self.quality.valueChanged.connect(lambda _v: self._timer.start())
        qrow.addWidget(self.quality, 1)
        qrow.addWidget(self.q_spin)
        form.addRow("质量", qrow)

        self.exif_check = QCheckBox("保留 EXIF 信息")
        self.exif_check.setChecked(True)
        form.addRow("", self.exif_check)
        v.addLayout(form)

        tip = QLabel("提示：JPG / WebP 支持质量参数；PNG / BMP / TIFF 为无损格式。")
        tip.setObjectName("subtitle")
        v.addWidget(tip)
        v.addStretch(1)
        return w

    def _tab_size(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)

        self.resize_check = QCheckBox("调整尺寸")
        self.resize_check.toggled.connect(lambda _v: self._timer.start())
        v.addWidget(self.resize_check)

        form = QFormLayout()
        form.setSpacing(8)
        self.size_mode = QComboBox()
        for key, label in [("long_edge", "限制长边"), ("width", "指定宽度"),
                           ("height", "指定高度"), ("percent", "按百分比")]:
            self.size_mode.addItem(label, key)
        self.size_mode.currentIndexChanged.connect(lambda _i: self._timer.start())
        form.addRow("方式", self.size_mode)

        srow = QHBoxLayout()
        self.val1 = QSpinBox()
        self.val1.setRange(1, 100000)
        self.val1.setValue(1920)
        self.val1.valueChanged.connect(lambda _v: self._timer.start())
        srow.addWidget(self.val1)
        srow.addWidget(QLabel("像素 / 百分比"))
        srow.addStretch(1)
        form.addRow("数值", srow)
        v.addLayout(form)

        self.budget_check = QCheckBox("限制文件体积")
        self.budget_check.toggled.connect(lambda _v: self._timer.start())
        v.addWidget(self.budget_check)

        brow = QHBoxLayout()
        self.budget_spin = QSpinBox()
        self.budget_spin.setRange(5, 200000)
        self.budget_spin.setValue(500)
        self.budget_spin.valueChanged.connect(lambda _v: self._timer.start())
        self.budget_unit = QComboBox()
        self.budget_unit.addItem("KB", 1024)
        self.budget_unit.addItem("MB", 1024 * 1024)
        self.budget_unit.currentIndexChanged.connect(lambda _i: self._timer.start())
        brow.addWidget(self.budget_spin)
        brow.addWidget(self.budget_unit)
        brow.addStretch(1)
        v.addLayout(brow)

        tip = QLabel("体积限制会优先降低质量；若仍不达标，会继续缩小尺寸。")
        tip.setObjectName("subtitle")
        v.addWidget(tip)
        v.addStretch(1)
        return w

    def _tab_output(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(8)

        self.radio_sub = QRadioButton("输出到子文件夹（保留原文件）")
        self.radio_sub.setChecked(True)
        sub_row = QHBoxLayout()
        sub_row.addSpacing(22)
        self.sub_name = QLineEdit("已处理")
        self.sub_name.setFixedWidth(180)
        sub_row.addWidget(self.sub_name)
        sub_row.addStretch(1)
        v.addWidget(self.radio_sub)
        v.addLayout(sub_row)

        self.radio_custom = QRadioButton("输出到指定文件夹")
        dir_row = QHBoxLayout()
        dir_row.addSpacing(22)
        self.dir_edit = QLineEdit()
        browse = QPushButton("浏览…")
        browse.setFixedWidth(72)
        browse.clicked.connect(self._browse_dir)
        dir_row.addWidget(self.dir_edit)
        dir_row.addWidget(browse)
        v.addWidget(self.radio_custom)
        v.addLayout(dir_row)

        self.radio_over = QRadioButton("直接覆盖原文件")
        v.addWidget(self.radio_over)
        warn = QLabel("覆盖模式会替换原文件，建议保留下面的备份选项。")
        warn.setObjectName("warn")
        warn.setStyleSheet("color:#c0392b;")
        warn.setContentsMargins(22, 0, 0, 0)
        v.addWidget(warn)

        self.backup_check = QCheckBox("覆盖前自动备份到 .picsprite_backup 文件夹")
        self.backup_check.setChecked(True)
        self.backup_check.setContentsMargins(22, 0, 0, 0)
        v.addWidget(self.backup_check)

        for r in (self.radio_sub, self.radio_custom, self.radio_over):
            r.toggled.connect(self._on_out_mode)
        self.sub_name.textChanged.connect(lambda _t: self._timer.start())
        self.dir_edit.textChanged.connect(lambda _t: self._timer.start())
        v.addStretch(1)
        self._on_out_mode()
        return w

    def _on_out_mode(self) -> None:
        self.sub_name.setEnabled(self.radio_sub.isChecked())
        self.dir_edit.setEnabled(self.radio_custom.isChecked())
        self._timer.start()

    def _browse_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择输出文件夹", self.dir_edit.text())
        if d:
            self.dir_edit.setText(d)
            self.radio_custom.setChecked(True)

    def _insert_token(self, token: str) -> None:
        le = self.pattern
        pos = le.cursorPosition()
        text = le.text()
        le.setText(text[:pos] + token + text[pos:])
        le.setCursorPosition(pos + len(token))
        le.setFocus()

    # ------------------------------------------------------------------ 选项
    def options(self) -> BatchOptions:
        opts = BatchOptions()
        opts.do_rename = self.rename_check.isChecked()
        opts.pattern = self.pattern.text().strip() or "{name}"
        opts.start_index = self.start_index.value()
        opts.padding = self.padding.value()
        opts.find_text = self.find_edit.text()
        opts.replace_text = self.replace_edit.text()
        opts.case_mode = self.case_box.currentData()

        opts.do_convert = self.convert_check.isChecked()
        opts.fmt = self.fmt_box.currentData()
        opts.quality = self.q_spin.value()
        opts.keep_exif = self.exif_check.isChecked()

        opts.do_resize = self.resize_check.isChecked()
        opts.resize_mode = self.size_mode.currentData()
        opts.resize_val1 = self.val1.value()
        opts.target_bytes = (int(self.budget_spin.value() * self.budget_unit.currentData())
                             if self.budget_check.isChecked() else 0)

        if self.radio_over.isChecked():
            opts.out_mode = "overwrite"
        elif self.radio_custom.isChecked():
            opts.out_mode = "custom"
            opts.out_dir = self.dir_edit.text().strip()
        else:
            opts.out_mode = "subfolder"
            opts.subfolder = self.sub_name.text().strip() or "已处理"
        opts.backup = self.backup_check.isChecked()
        return opts

    # ------------------------------------------------------------------ 预览
    def _refresh_preview(self) -> None:
        if self._running:
            return
        opts = self.options()
        plan = build_plan(self.paths, opts)
        show = plan[:300]
        self.table.setRowCount(len(show))
        changed = 0
        conflicts = 0
        for i, item in enumerate(show):
            self.table.setItem(i, 0, QTableWidgetItem(os.path.basename(item.src)))
            new_name = os.path.basename(item.dst)
            self.table.setItem(i, 1, QTableWidgetItem(new_name))
            self.table.setItem(i, 2, QTableWidgetItem(item.action))
            st = QTableWidgetItem(item.status or "就绪")
            if item.status.startswith("与前面"):
                st.setForeground(Qt.GlobalColor.darkRed)
                conflicts += 1
            self.table.setItem(i, 3, st)
            if new_name != os.path.basename(item.src):
                changed += 1
        note = f"共 {len(plan)} 个文件，{changed} 个文件名将发生变化"
        if conflicts:
            note += f"，{conflicts} 个重名将被跳过"
        if len(plan) > len(show):
            note += f"（预览仅显示前 {len(show)} 项）"
        self.preview_note.setText(note)

        # 命名示例
        if opts.do_rename and plan:
            a = os.path.basename(plan[0].dst)
            b = os.path.basename(plan[min(1, len(plan) - 1)].dst)
            self.example.setText(f"示例：{a}　{b}")

        self.btn_start.setEnabled(bool(self.paths) and (
            opts.do_rename or opts.do_convert or opts.do_resize or opts.target_bytes))

    # ------------------------------------------------------------------ 执行
    def _start(self) -> None:
        if not self.paths:
            return
        opts = self.options()
        if not (opts.do_rename or opts.do_convert or opts.do_resize or opts.target_bytes):
            QMessageBox.information(self, "提示", "请至少勾选一项操作：重命名 / 转换格式 / 调整尺寸")
            return
        if opts.out_mode == "overwrite":
            ret = QMessageBox.question(
                self, "确认覆盖",
                f"将直接修改 {len(self.paths)} 个原文件。\n"
                + ("已勾选自动备份，可在 .picsprite_backup 里找回。\n"
                   if opts.backup else "未勾选备份，操作不可撤销！\n")
                + "确定继续吗？")
            if ret != QMessageBox.StandardButton.Yes:
                return
        if opts.out_mode == "custom" and not os.path.isdir(opts.out_dir):
            QMessageBox.warning(self, "提示", "输出文件夹不存在，请重新选择")
            return

        self._running = True
        self._set_ui_enabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, len(self.paths))
        self.progress.setValue(0)
        self.btn_stop.setVisible(True)
        self.status.setText("正在处理…")

        sig = Signals()
        sig.progress.connect(self._on_progress)
        sig.finished.connect(self._on_finished)
        sig.error.connect(self._on_error)
        self._task = BatchTask(self.paths, opts, sig)
        from PySide6.QtCore import QThreadPool
        QThreadPool.globalInstance().start(self._task)

    def _set_ui_enabled(self, on: bool) -> None:
        self.tabs.setEnabled(on)
        self.btn_start.setEnabled(on)
        self.btn_close.setEnabled(on)

    def _on_progress(self, i: int, total: int, name: str) -> None:
        self.progress.setMaximum(max(1, total))
        self.progress.setValue(i)
        if name:
            self.status.setText(f"正在处理 {i + 1}/{total}：{name}")

    def _on_finished(self, summary: dict) -> None:
        self._running = False
        self.btn_stop.setVisible(False)
        self._set_ui_enabled(True)
        self.progress.setValue(self.progress.maximum())
        done = summary.get("done", 0)
        failed = summary.get("failed", [])
        self.status.setText(f"完成 {done} 个，失败 {len(failed)} 个")
        msg = f"处理完成：{done} 个文件"
        if failed:
            msg += f"\n失败 {len(failed)} 个：\n" + "\n".join(failed[:8])
            if len(failed) > 8:
                msg += f"\n… 另有 {len(failed) - 8} 个"
        QMessageBox.information(self, "批量处理", msg)
        self.finished.emit()
        self.progress.setVisible(False)

    def _on_error(self, msg: str) -> None:
        self._running = False
        self.btn_stop.setVisible(False)
        self._set_ui_enabled(True)
        self.progress.setVisible(False)
        QMessageBox.critical(self, "批量处理失败", msg)

    def _stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self.status.setText("正在停止…")
            self.btn_stop.setEnabled(False)
