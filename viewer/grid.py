# -*- coding: utf-8 -*-
"""缩略图浏览页：异步加载 + 磁盘缓存 + 排序 / 搜索 / 尺寸调节。"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QSlider,
                               QVBoxLayout, QWidget)

from . import icons, imageio
from .batch import sort_files
from .thumbcache import ThumbCache
from .workers import TaskPool, ThumbTask

SORTS = [
    ("name_asc", "名称 ↑"),
    ("name_desc", "名称 ↓"),
    ("date_desc", "修改时间 ↓"),
    ("date_asc", "修改时间 ↑"),
    ("size_desc", "文件大小 ↓"),
    ("size_asc", "文件大小 ↑"),
]


class ThumbGrid(QListWidget):
    openRequested = Signal(str)
    contextRequested = Signal(object, object)     # 全局坐标, 选中路径列表

    def __init__(self, cache: ThumbCache, parent=None) -> None:
        super().__init__(parent)
        self.cache = cache
        self.pool = TaskPool(4)
        self._generation = 0
        self._pending: set = set()
        self._path_items: Dict[str, QListWidgetItem] = {}
        self._paths: List[str] = []
        self._thumb = 172
        self._all_paths: List[str] = []

        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Static)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setWordWrap(True)
        self.setSpacing(6)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context)
        self.itemDoubleClicked.connect(self._on_double)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(70)
        self._timer.timeout.connect(self._load_visible)

        self.verticalScrollBar().valueChanged.connect(lambda _v: self._timer.start())
        self.horizontalScrollBar().valueChanged.connect(lambda _v: self._timer.start())

    # ----------------------------------------------------------- 数据
    def set_files(self, folder: str, files: List[str], thumb: int = 172) -> None:
        self._generation += 1
        self._pending.clear()
        self._folder = folder
        self._all_paths = list(files)
        self._thumb = thumb
        self.apply_filter("")

    def apply_filter(self, text: str, sort_mode: str = "name_asc") -> None:
        text = (text or "").strip().lower()
        files = [p for p in self._all_paths if text in os.path.basename(p).lower()] if text else list(self._all_paths)
        self._paths = sort_files(files, sort_mode)
        self._rebuild()

    def set_sort(self, mode: str) -> None:
        self._paths = sort_files(self._paths, mode)
        self._rebuild()

    def set_thumb_size(self, size: int) -> None:
        self._thumb = int(size)
        self.setIconSize(QSize(self._thumb, self._thumb))
        self.setGridSize(QSize(self._thumb + 26, self._thumb + 42))
        for path, item in self._path_items.items():
            item.setIcon(QIcon(self._placeholder(path)))
        self._generation += 1
        self._pending.clear()
        self._load_visible()

    def _rebuild(self) -> None:
        self.clear()
        self._path_items.clear()
        self.setIconSize(QSize(self._thumb, self._thumb))
        self.setGridSize(QSize(self._thumb + 26, self._thumb + 42))
        for p in self._paths:
            item = QListWidgetItem(QIcon(self._placeholder(p)), os.path.basename(p))
            item.setData(Qt.ItemDataRole.UserRole, p)
            item.setToolTip(f"{os.path.basename(p)}\n{p}")
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self.addItem(item)
            self._path_items[p] = item
        self._timer.start()

    def _placeholder(self, path: str) -> QPixmap:
        s = self._thumb
        pm = QPixmap(s, s)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#eef0f4"))
        p.drawRoundedRect(0, 0, s, s, 8, 8)
        p.setPen(QColor("#aab1bd"))
        f = QFont()
        f.setPointSize(max(7, int(s / 12)))
        f.setBold(True)
        p.setFont(f)
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, imageio.format_label(path))
        p.end()
        return pm

    # ----------------------------------------------------------- 异步缩略图
    def _load_visible(self) -> None:
        if not self._paths:
            return
        gen = self._generation
        rect = self.viewport().rect().adjusted(-200, -200, 200, 400)
        for path, item in self._path_items.items():
            if item.isHidden():
                continue
            if not rect.intersects(self.visualItemRect(item)):
                continue
            if item.data(Qt.ItemDataRole.UserRole + 1) == "done":
                continue
            if path in self._pending:
                continue
            self._pending.add(path)
            task = ThumbTask(path, self._thumb, self.cache, gen)
            task.signals.result.connect(self._on_thumb)
            self.pool.start(task)

    def _on_thumb(self, payload) -> None:
        path, qimg, gen = payload
        self._pending.discard(path)
        if gen != self._generation:
            return
        item = self._path_items.get(path)
        if item is None:
            return
        if qimg is None or qimg.isNull():
            item.setData(Qt.ItemDataRole.UserRole + 1, "done")
            return
        from PySide6.QtGui import QPixmap
        pm = QPixmap.fromImage(qimg)
        if pm.width() > self._thumb or pm.height() > self._thumb:
            pm = pm.scaled(self._thumb, self._thumb, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        item.setIcon(QIcon(pm))
        item.setData(Qt.ItemDataRole.UserRole + 1, "done")
        item.setSizeHint(QSize(self._thumb + 20, self._thumb + 40))

    def _request_item(self, path: str, force: bool = False) -> None:
        item = self._path_items.get(path)
        if item is None:
            return
        if force:
            item.setData(Qt.ItemDataRole.UserRole + 1, "")
            task = ThumbTask(path, self._thumb, self.cache, self._generation)
            task.signals.result.connect(self._on_thumb)
            self._pending.add(path)
            self.pool.start(task)

    # ----------------------------------------------------------- 交互
    def selected_paths(self) -> List[str]:
        return [i.data(Qt.ItemDataRole.UserRole) for i in self.selectedItems()]

    def current_path(self) -> Optional[str]:
        it = self.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def select_path(self, path: str) -> None:
        item = self._path_items.get(path)
        if item is not None:
            self.setCurrentItem(item)
            self.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)

    def _on_double(self, item: QListWidgetItem) -> None:
        self.openRequested.emit(item.data(Qt.ItemDataRole.UserRole))

    def _on_context(self, pos: QPoint) -> None:
        item = self.itemAt(pos)
        if item is not None and not item.isSelected():
            self.clearSelection()
            item.setSelected(True)
            self.setCurrentItem(item)
        paths = self.selected_paths()
        if item is None and not paths:
            paths = []
        self.contextRequested.emit(self.viewport().mapToGlobal(pos), paths)

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self._timer.start()


class GridPage(QWidget):
    openRequested = Signal(str)
    contextRequested = Signal(object, object)
    selectionCountChanged = Signal(int)

    def __init__(self, cache: ThumbCache, thumb_size: int = 172, sort_mode: str = "name_asc",
                 parent=None) -> None:
        super().__init__(parent)
        self._folder = ""
        self._all: List[str] = []

        bar = QHBoxLayout()
        bar.setContentsMargins(10, 8, 10, 6)
        bar.setSpacing(8)

        self.search = QLineEdit()
        self.search.setPlaceholderText("在文件名中筛选…")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(220)
        self.search.textChanged.connect(self._apply)

        self.sort_box = QComboBox()
        for key, label in SORTS:
            self.sort_box.addItem(label, key)
        self.sort_box.currentIndexChanged.connect(self._apply)

        self.count_label = QLabel("0 张")
        self.count_label.setObjectName("subtitle")

        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(96, 320)
        self.size_slider.setValue(thumb_size)
        self.size_slider.setFixedWidth(120)
        self.size_slider.setToolTip("缩略图大小")
        self.size_slider.valueChanged.connect(self._on_size)

        bar.addWidget(self.search)
        bar.addWidget(self.sort_box)
        bar.addStretch(1)
        bar.addWidget(QLabel("缩略图"))
        bar.addWidget(self.size_slider)
        bar.addWidget(self.count_label)

        self.grid = ThumbGrid(cache)
        self.grid.openRequested.connect(self.openRequested)
        self.grid.contextRequested.connect(self.contextRequested)
        self.grid.itemSelectionChanged.connect(
            lambda: self.selectionCountChanged.emit(len(self.grid.selectedItems())))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 0, 10, 10)
        lay.setSpacing(6)
        lay.addLayout(bar)
        lay.addWidget(self.grid)

        self._set_sort_index(sort_mode)

    def _set_sort_index(self, mode: str) -> None:
        for i in range(self.sort_box.count()):
            if self.sort_box.itemData(i) == mode:
                self.sort_box.setCurrentIndex(i)
                return

    def _on_size(self, value: int) -> None:
        self.grid.set_thumb_size(value)
        self.grid._thumb_size_value = value

    def thumb_size(self) -> int:
        return self.size_slider.value()

    def set_folder(self, folder: str, files: List[str]) -> None:
        self._folder = folder
        self._all = list(files)
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.grid.set_files(folder, files, self.thumb_size())
        self.count_label.setText(f"{len(files)} 张")

    def refresh(self, files: Optional[List[str]] = None) -> None:
        if files is not None:
            self._all = list(files)
        self.grid.set_files(self._folder, self._all, self.thumb_size())
        self.count_label.setText(f"{len(self._all)} 张")

    def _apply(self) -> None:
        mode = self.sort_box.currentData() or "name_asc"
        self.grid.apply_filter(self.search.text(), mode)
        self.count_label.setText(f"{self.grid.count()} / {len(self._all)} 张")

    def set_sort(self, mode: str) -> None:
        self._set_sort_index(mode)
        self._apply()

    def sort_mode(self) -> str:
        return self.sort_box.currentData() or "name_asc"

    def files(self) -> List[str]:
        return list(self._all)

    def selected_paths(self) -> List[str]:
        return self.grid.selected_paths()

    def select_path(self, path: str) -> None:
        self.grid.select_path(path)

    def current_path(self) -> Optional[str]:
        return self.grid.current_path()
