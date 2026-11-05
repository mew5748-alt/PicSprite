# -*- coding: utf-8 -*-
"""设置对话框：常规偏好、快捷键自定义、右键菜单个性化、缓存管理。"""
from __future__ import annotations

from typing import List

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QHeaderView, QLabel, QKeySequenceEdit,
                               QListWidget, QListWidgetItem, QMessageBox,
                               QPushButton, QSpinBox, QTabWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from . import util
from .config import ACTION_MAP, ACTIONS, settings
from .grid import SORTS
from .thumbcache import ThumbCache


class SettingsDialog(QDialog):
    applied = Signal()

    def __init__(self, cache: ThumbCache, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(640, 560)
        self.cache = cache
        self._shortcut_editors = {}
        self._build()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        tabs = QTabWidget()
        tabs.addTab(self._tab_general(), "常规")
        tabs.addTab(self._tab_shortcuts(), "快捷键")
        tabs.addTab(self._tab_context(), "右键菜单")
        tabs.addTab(self._tab_cache(), "缓存")
        root.addWidget(tabs, 1)

        btns = QDialogButtonBox()
        ok = btns.addButton("保存设置", QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setDefault(True)
        btns.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _tab_general(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(10)

        box1 = QGroupBox("浏览")
        f1 = QFormLayout(box1)
        f1.setSpacing(8)
        self.open_last = QCheckBox("启动时打开上次浏览的文件夹")
        self.open_last.setChecked(settings.get_bool("general/open_last", True))
        f1.addRow("", self.open_last)

        self.loop = QCheckBox("幻灯片播放到末尾后循环")
        self.loop.setChecked(settings.get_bool("general/loop", True))
        f1.addRow("", self.loop)

        self.slide_interval = QSpinBox()
        self.slide_interval.setRange(1, 60)
        self.slide_interval.setValue(settings.get_int("general/slideshow_interval", 3))
        self.slide_interval.setSuffix(" 秒")
        f1.addRow("幻灯片间隔", self.slide_interval)

        self.sort_box = QComboBox()
        for key, label in SORTS:
            self.sort_box.addItem(label, key)
        idx = max(0, self.sort_box.findData(settings.get("general/sort", "name_asc")))
        self.sort_box.setCurrentIndex(idx)
        f1.addRow("默认排序", self.sort_box)

        self.thumb_size = QSpinBox()
        self.thumb_size.setRange(96, 320)
        self.thumb_size.setValue(settings.get_int("general/thumb_size", 172))
        self.thumb_size.setSuffix(" 像素")
        f1.addRow("缩略图墙大小", self.thumb_size)

        self.show_strip = QCheckBox("看图时在左侧显示缩略图栏")
        self.show_strip.setChecked(settings.get_bool("view/show_strip", True))
        f1.addRow("", self.show_strip)

        self.strip_size = QSpinBox()
        self.strip_size.setRange(72, 220)
        self.strip_size.setValue(settings.get_int("general/strip_size", 104))
        self.strip_size.setSuffix(" 像素")
        f1.addRow("缩略图栏大小", self.strip_size)

        self.folder_to_grid = QCheckBox("打开文件夹时先显示整页缩略图")
        self.folder_to_grid.setChecked(settings.get_bool("view/folder_to_grid", True))
        f1.addRow("", self.folder_to_grid)
        v.addWidget(box1)

        box2 = QGroupBox("显示与保存")
        f2 = QFormLayout(box2)
        f2.setSpacing(8)
        self.bg_box = QComboBox()
        self.bg_box.addItem("深灰（推荐，看图更准）", "dark")
        self.bg_box.addItem("中灰", "mid")
        self.bg_box.addItem("浅色", "light")
        idx = max(0, self.bg_box.findData(settings.get("view/canvas_bg", "dark")))
        self.bg_box.setCurrentIndex(idx)
        f2.addRow("画布背景", self.bg_box)

        self.smooth = QCheckBox("放大时使用平滑插值")
        self.smooth.setChecked(settings.get_bool("general/smooth_zoom", True))
        f2.addRow("", self.smooth)

        self.backup = QCheckBox("覆盖保存前自动备份原图")
        self.backup.setChecked(settings.get_bool("general/backup_before_overwrite", True))
        f2.addRow("", self.backup)

        self.confirm_delete = QCheckBox("删除文件前二次确认")
        self.confirm_delete.setChecked(settings.get_bool("general/confirm_delete", True))
        f2.addRow("", self.confirm_delete)
        v.addWidget(box2)
        v.addStretch(1)
        return w

    def _tab_shortcuts(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)

        tip = QLabel("点击右侧输入框，直接按下想用的组合键即可。留空表示不绑定快捷键。")
        tip.setObjectName("subtitle")
        v.addWidget(tip)

        table = QTableWidget(len(ACTIONS), 3)
        table.setHorizontalHeaderLabels(["分类", "功能", "快捷键"])
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.setColumnWidth(0, 60)
        table.setColumnWidth(1, 190)
        for i, a in enumerate(ACTIONS):
            table.setItem(i, 0, QTableWidgetItem(a.category))
            table.setItem(i, 1, QTableWidgetItem(a.text))
            editor = QKeySequenceEdit()
            editor.setKeySequence(QKeySequence(settings.shortcut(a.id)))
            table.setCellWidget(i, 2, editor)
            self._shortcut_editors[a.id] = editor
        table.resizeRowsToContents()
        v.addWidget(table, 1)

        row = QHBoxLayout()
        btn_reset = QPushButton("恢复默认快捷键")
        btn_reset.clicked.connect(self._reset_shortcuts)
        row.addWidget(btn_reset)
        row.addStretch(1)
        v.addLayout(row)
        return w

    def _reset_shortcuts(self) -> None:
        for a in ACTIONS:
            self._shortcut_editors[a.id].setKeySequence(QKeySequence(a.shortcut))

    def _tab_context(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)

        tip = QLabel("勾选的项目会出现在图片的右键菜单里，可用右侧按钮调整顺序。")
        tip.setObjectName("subtitle")
        v.addWidget(tip)

        self.ctx_list = QListWidget()
        for aid, visible in settings.context_items():
            if aid not in ACTION_MAP:
                continue
            item = QListWidgetItem(f"{ACTION_MAP[aid].text}　·　{ACTION_MAP[aid].category}")
            item.setData(Qt.ItemDataRole.UserRole, aid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if visible else Qt.CheckState.Unchecked)
            self.ctx_list.addItem(item)
        v.addWidget(self.ctx_list, 1)

        row = QHBoxLayout()
        up = QPushButton("上移")
        up.clicked.connect(lambda: self._move_ctx(-1))
        down = QPushButton("下移")
        down.clicked.connect(lambda: self._move_ctx(1))
        all_on = QPushButton("全选")
        all_on.clicked.connect(lambda: self._set_all_ctx(True))
        all_off = QPushButton("全不选")
        all_off.clicked.connect(lambda: self._set_all_ctx(False))
        for b in (up, down):
            row.addWidget(b)
        row.addSpacing(16)
        row.addWidget(all_on)
        row.addWidget(all_off)
        row.addStretch(1)
        v.addLayout(row)
        return w

    def _move_ctx(self, delta: int) -> None:
        row = self.ctx_list.currentRow()
        if row < 0:
            return
        new = row + delta
        if not (0 <= new < self.ctx_list.count()):
            return
        item = self.ctx_list.takeItem(row)
        self.ctx_list.insertItem(new, item)
        self.ctx_list.setCurrentRow(new)

    def _set_all_ctx(self, on: bool) -> None:
        state = Qt.CheckState.Checked if on else Qt.CheckState.Unchecked
        for i in range(self.ctx_list.count()):
            self.ctx_list.item(i).setCheckState(state)

    def _tab_cache(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(10)

        box = QGroupBox("缩略图缓存")
        f = QFormLayout(box)
        f.setSpacing(8)
        self.cache_path = QLabel(self.cache.dir)
        self.cache_path.setWordWrap(True)
        self.cache_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        f.addRow("缓存目录", self.cache_path)

        self.cache_size = QLabel("计算中…")
        f.addRow("当前占用", self.cache_size)

        self.cache_max = QSpinBox()
        self.cache_max.setRange(100, 20000)
        self.cache_max.setSingleStep(100)
        self.cache_max.setValue(settings.get_int("cache/max_mb", 800))
        self.cache_max.setSuffix(" MB")
        f.addRow("上限", self.cache_max)
        v.addWidget(box)

        row = QHBoxLayout()
        btn_clear = QPushButton("清空缓存")
        btn_clear.clicked.connect(self._clear_cache)
        btn_open = QPushButton("打开缓存目录")
        btn_open.clicked.connect(lambda: util.open_folder(self.cache.dir))
        row.addWidget(btn_clear)
        row.addWidget(btn_open)
        row.addStretch(1)
        v.addLayout(row)

        tip = QLabel("缓存按「路径 + 修改时间 + 缩略图尺寸」存储，图片改动后会自动失效。")
        tip.setObjectName("subtitle")
        tip.setWordWrap(True)
        v.addWidget(tip)
        v.addStretch(1)

        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, self._update_cache_size)
        return w

    def _update_cache_size(self) -> None:
        n = self.cache.count_files()
        self.cache_size.setText(f"{util.human_size(self.cache.size_bytes())}　（{n} 个文件）")

    def _clear_cache(self) -> None:
        if QMessageBox.question(self, "清空缓存", "确定要清空所有缩略图缓存吗？") \
                != QMessageBox.StandardButton.Yes:
            return
        self.cache.clear()
        self._update_cache_size()

    # ------------------------------------------------------------------ 保存
    def accept(self) -> None:
        # 快捷键重复检查
        used = {}
        dups: List[str] = []
        values = {}
        for a in ACTIONS:
            seq = self._shortcut_editors[a.id].keySequence().toString(
                QKeySequence.SequenceFormat.PortableText)
            values[a.id] = seq
            if not seq:
                continue
            if seq in used:
                dups.append(f"{ACTION_MAP[used[seq]].text} ↔ {a.text}（{seq}）")
            else:
                used[seq] = a.id
        if dups:
            QMessageBox.warning(self, "快捷键冲突",
                                "以下功能使用了相同的快捷键，请调整：\n\n" + "\n".join(dups))
            return

        for aid, seq in values.items():
            settings.set_shortcut(aid, seq)

        settings.set("general/open_last", self.open_last.isChecked())
        settings.set("general/loop", self.loop.isChecked())
        settings.set("general/slideshow_interval", self.slide_interval.value())
        settings.set("general/sort", self.sort_box.currentData())
        settings.set("general/thumb_size", self.thumb_size.value())
        settings.set("general/strip_size", self.strip_size.value())
        settings.set("view/show_strip", self.show_strip.isChecked())
        settings.set("view/folder_to_grid", self.folder_to_grid.isChecked())
        settings.set("view/canvas_bg", self.bg_box.currentData())
        settings.set("general/smooth_zoom", self.smooth.isChecked())
        settings.set("general/backup_before_overwrite", self.backup.isChecked())
        settings.set("general/confirm_delete", self.confirm_delete.isChecked())
        settings.set("cache/max_mb", self.cache_max.value())
        self.cache.max_bytes = self.cache_max.value() * 1024 * 1024

        items = []
        for i in range(self.ctx_list.count()):
            it = self.ctx_list.item(i)
            items.append([it.data(Qt.ItemDataRole.UserRole),
                          it.checkState() == Qt.CheckState.Checked])
        settings.set_context_items(items)

        self.applied.emit()
        super().accept()
