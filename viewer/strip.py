# -*- coding: utf-8 -*-
"""左侧缩略图条：看单图时同步显示当前文件夹的全部图片，单击即可切换。

与 grid.py 的整页缩略图墙共用 ThumbCache / ThumbTask，只加载可视区域，
因此即使文件夹里有几千张图也不会卡。
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel,
                               QListWidget, QListWidgetItem, QStyle,
                               QStyledItemDelegate, QStyleOptionViewItem,
                               QVBoxLayout, QWidget)

from . import imageio
from .thumbcache import ThumbCache
from .workers import TaskPool, ThumbTask

# item 上存的自定义数据
_ROLE_PATH = Qt.ItemDataRole.UserRole
_ROLE_STATE = Qt.ItemDataRole.UserRole + 1


class StripDelegate(QStyledItemDelegate):
    """缩略图居中、文件名在下方一行，选中时整格淡蓝高亮。"""

    def __init__(self, icon_w: int, icon_h: int, parent=None) -> None:
        super().__init__(parent)
        self.icon_w = icon_w
        self.icon_h = icon_h
        self.cell_w = icon_w + 8
        self.font = QFont()
        self.font.setPointSize(8)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem,
              index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = option.rect.adjusted(2, 1, -2, -1)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#e3ecff" if selected else "#f3f6fd"))
            painter.drawRoundedRect(r, 7, 7)

        top = r.top() + 3
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(icon, QIcon):
            pm = icon.pixmap(QSize(self.icon_w, self.icon_h))
            if not pm.isNull():
                x = r.left() + max(0, (r.width() - pm.width()) // 2)
                y = top + max(0, (self.icon_h - pm.height()) // 2)
                painter.drawPixmap(x, y, pm)

        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        tr = QRect(r.left() + 5, top + self.icon_h + 2, max(10, r.width() - 10), 15)
        painter.setFont(self.font)
        painter.setPen(QColor("#1656d6" if selected else "#4a5160"))
        fm = painter.fontMetrics()
        painter.drawText(tr, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                         fm.elidedText(text, Qt.TextElideMode.ElideMiddle, tr.width()))
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(self.cell_w, self.icon_h + 22)


class ThumbStrip(QListWidget):
    """单列纵向缩略图条。"""

    openRequested = Signal(str)

    def __init__(self, cache: ThumbCache, thumb_size: int = 104, parent=None) -> None:
        super().__init__(parent)
        self.cache = cache
        self.pool = TaskPool(2)
        self._gen = 0
        self._pending: set = set()
        self._items: Dict[str, QListWidgetItem] = {}
        self._files: List[str] = []
        self._folder = ""
        self._thumb = max(72, int(thumb_size))
        self._ph_cache: Dict[str, QPixmap] = {}

        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setFlow(QListWidget.Flow.TopToBottom)
        self.setWrapping(False)          # 单列纵向排列，超出就滚动
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Static)
        self.setUniformItemSizes(True)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSpacing(2)
        self.setObjectName("thumbStrip")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self.itemClicked.connect(self._on_clicked)

        self._delegate = StripDelegate(self._thumb, int(round(self._thumb * 0.75)), self)
        self.setItemDelegate(self._delegate)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(60)
        self._timer.timeout.connect(self._load_visible)
        self.verticalScrollBar().valueChanged.connect(lambda _v: self._timer.start())

        self._apply_metrics()

    # ------------------------------------------------------------ 尺寸
    def _apply_metrics(self) -> None:
        w = self._thumb
        h = int(round(w * 0.75))
        self._icon_w, self._icon_h = w, h
        if getattr(self, "_ph_cache", None) is not None:
            self._ph_cache.clear()
        self.setIconSize(QSize(w, h))
        if getattr(self, "_delegate", None) is not None:
            self._delegate.icon_w = w
            self._delegate.icon_h = h
        self._grid_w = self._cell_width()
        if getattr(self, "_delegate", None) is not None:
            self._delegate.cell_w = self._grid_w
        self.setGridSize(QSize(self._grid_w, h + 22))
        if getattr(self, "_delegate", None) is not None:
            self.viewport().update()

    def _cell_width(self) -> int:
        vw = self.viewport().width() if self.viewport() else 0
        return max(self._thumb + 8, vw - 2)

    def _sync_cell_width(self) -> None:
        w = self._cell_width()
        if abs(w - getattr(self, "_grid_w", 0)) < 4:
            return
        self._grid_w = w
        size = QSize(w, self._icon_h + 22)
        self.setGridSize(size)
        if getattr(self, "_delegate", None) is not None:
            self._delegate.cell_w = w
        for item in self._items.values():
            item.setSizeHint(size)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_cell_width()
        # viewport 的实际宽度可能晚一步更新，事件循环末尾再校一次
        QTimer.singleShot(0, self._sync_cell_width)

    def set_thumb_size(self, size: int) -> None:
        size = max(72, min(220, int(size)))
        if size == self._thumb:
            return
        self._thumb = size
        self._apply_metrics()
        self._gen += 1
        self._pending.clear()
        for p, item in self._items.items():
            item.setIcon(QIcon(self._placeholder(p)))
            item.setData(_ROLE_STATE, "")
            item.setSizeHint(self.gridSize())
        self._timer.start()

    def thumb_size(self) -> int:
        return self._thumb

    # ------------------------------------------------------------ 数据
    def set_files(self, folder: str, files: List[str]) -> None:
        self._gen += 1
        self._pending.clear()
        self._folder = folder or ""
        self._files = list(files)
        self._items.clear()
        self.blockSignals(True)
        self.clear()
        self.blockSignals(False)

        if not self._files:
            tip = QListWidgetItem("（没有图片）")
            tip.setFlags(Qt.ItemFlag.NoItemFlags)
            tip.setForeground(QColor("#9aa0a8"))
            f = QFont()
            f.setPointSize(9)
            tip.setFont(f)
            tip.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.addItem(tip)
            return

        for p in self._files:
            item = QListWidgetItem(QIcon(self._placeholder(p)), os.path.basename(p))
            item.setData(_ROLE_PATH, p)
            item.setToolTip(f"{os.path.basename(p)}\n{p}")
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
            item.setSizeHint(self.gridSize())
            self.addItem(item)
            self._items[p] = item
        self._timer.start()

    def files(self) -> List[str]:
        return list(self._files)

    def _placeholder(self, path: str) -> QPixmap:
        """按格式生成占位图；同类格式复用同一张，几千张图也不会卡。"""
        label = imageio.format_label(path)
        hit = self._ph_cache.get(label)
        if hit is not None:
            return hit
        w, h = self._icon_w, self._icon_h
        pm = QPixmap(w, h)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#eef0f4"))
        p.drawRoundedRect(0, 0, w, h, 6, 6)
        p.setPen(QColor("#aab1bd"))
        f = QFont()
        f.setPointSize(max(7, int(w / 14)))
        f.setBold(True)
        p.setFont(f)
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, label)
        p.end()
        self._ph_cache[label] = pm
        return pm

    # ------------------------------------------------------------ 异步缩略图
    def _load_visible(self) -> None:
        if not self._items:
            return
        gen = self._gen
        rect = self.viewport().rect().adjusted(0, -120, 0, 240)
        for path, item in self._items.items():
            if item.data(_ROLE_STATE) == "done" or path in self._pending:
                continue
            if not rect.intersects(self.visualItemRect(item)):
                continue
            self._pending.add(path)
            task = ThumbTask(path, self._thumb, self.cache, gen)
            task.signals.result.connect(self._on_thumb)
            self.pool.start(task)

    def _on_thumb(self, payload) -> None:
        path, qimg, gen = payload
        self._pending.discard(path)
        if gen != self._gen:
            return
        item = self._items.get(path)
        if item is None:
            return
        item.setData(_ROLE_STATE, "done")
        if qimg is None or qimg.isNull():
            return
        pm = QPixmap.fromImage(qimg)
        if pm.width() > self._icon_w or pm.height() > self._icon_h:
            pm = pm.scaled(self._icon_w, self._icon_h,
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        item.setIcon(QIcon(pm))

    # ------------------------------------------------------------ 交互
    def set_current(self, path: Optional[str], scroll: bool = True) -> None:
        """高亮当前打开的图片（不触发打开）。"""
        if not path:
            return
        item = self._items.get(path)
        if item is None:
            return
        if self.currentItem() is item and item.isSelected():
            return
        self.blockSignals(True)
        self.setCurrentItem(item)
        item.setSelected(True)
        self.blockSignals(False)
        if scroll:
            self.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)
            self._timer.start()

    def current_path(self) -> Optional[str]:
        it = self.currentItem()
        return it.data(_ROLE_PATH) if it else None

    def _on_clicked(self, item: QListWidgetItem) -> None:
        path = item.data(_ROLE_PATH)
        if path:
            self.openRequested.emit(str(path))

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            path = self.current_path()
            if path:
                self.openRequested.emit(path)
                return
        super().keyPressEvent(event)


class StripPanel(QWidget):
    """带标题与计数的缩略图条容器。"""

    openRequested = Signal(str)

    def __init__(self, cache: ThumbCache, thumb_size: int = 104, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("stripPanel")

        self.title = QLabel("缩略图")
        self.title.setObjectName("subtitle")
        self.count = QLabel("0 张")
        self.count.setStyleSheet("color:#9aa0a8;")

        head = QWidget()
        hl = QHBoxLayout(head)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)
        hl.addWidget(self.title)
        hl.addStretch(1)
        hl.addWidget(self.count)

        self.strip = ThumbStrip(cache, thumb_size)
        self.strip.openRequested.connect(self.openRequested)

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 6, 0, 2)
        v.setSpacing(4)
        v.addWidget(head)
        v.addWidget(self.strip, 1)

        self.setMinimumHeight(150)

    def set_folder(self, folder: str, files: List[str]) -> None:
        self.strip.set_files(folder, files)
        self.count.setText(f"{len(files)} 张")

    def set_current(self, path: Optional[str]) -> None:
        self.strip.set_current(path)

    def set_thumb_size(self, size: int) -> None:
        self.strip.set_thumb_size(size)
