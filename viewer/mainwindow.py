# -*- coding: utf-8 -*-
"""主窗口：菜单、工具栏、目录树、缩略图墙、信息面板与全部功能入口。"""
from __future__ import annotations

import datetime
import os
import shutil
from typing import List, Optional

from PySide6.QtCore import QDir, QModelIndex, QPoint, QSize, Qt, QTimer
from PySide6.QtGui import (QAction, QColor, QFont, QGuiApplication, QImage,
                           QKeySequence, QPixmap)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDockWidget,
                               QFileDialog, QFileSystemModel, QFormLayout, QFrame,
                               QHBoxLayout, QInputDialog, QLabel, QMainWindow,
                               QMenu, QMessageBox, QPushButton, QSizePolicy,
                               QSlider, QSplitter, QStackedWidget, QStatusBar,
                               QToolBar, QToolButton, QTreeView, QVBoxLayout,
                               QWidget, QColorDialog)

from . import icons, imageio, printing, util
from .batch import sort_files
from .batchdialog import BatchDialog
from .canvas import MODE_CROP, MODE_DRAW, MODE_TEXT, MODE_VIEW, ImageCanvas
from .config import ACTION_MAP, ACTIONS, APP_NAME, APP_VERSION, cache_dir, settings
from .dialogs import (ColorButton, CompressDialog, PropertiesDialog, ResizeDialog,
                      SaveAsDialog, ShortcutsDialog, TextDialog, about_text)
from .grid import GridPage
from .printdialog import PrintDialog
from .printing import PrintItem, PrintOptions
from .settingsdialog import SettingsDialog
from .style import CANVAS_COLORS
from .thumbcache import ThumbCache
from .workers import LoadTask, TaskPool

MENU_ORDER = ["文件", "编辑", "图片", "视图", "工具", "帮助"]

MENU_LAYOUT = {
    "文件": ["file.open", "file.open_folder", "-", "file.save", "file.save_as",
             "file.compress", "-", "file.print", "file.print_preview", "-",
             "file.rename", "file.delete", "-",
             "file.properties", "-", "file.quit"],
    "编辑": ["edit.undo", "edit.redo", "-", "edit.crop", "edit.draw", "edit.text",
             "edit.resize", "-", "file.copy_image", "file.paste_image",
             "file.copy_path", "-", "edit.reset"],
    "图片": ["image.rot_left", "image.rot_right", "image.flip_h", "image.flip_v"],
    "视图": ["view.grid", "view.fullscreen", "view.slideshow", "-",
             "view.zoom_in", "view.zoom_out", "view.fit", "view.actual", "-",
             "view.prev", "view.next", "view.first", "view.last", "-",
             "view.frame_prev", "view.frame_next", "view.animate", "-",
             "view.info", "view.bg"],
    "工具": ["tools.batch", "tools.settings", "-", "tools.wallpaper", "tools.reveal",
             "-", "tools.clear_cache", "tools.open_cache"],
    "帮助": ["help.shortcuts", "-", "help.about"],
}

TOOLBAR_ITEMS = [
    "file.open", "file.open_folder", "|",
    "view.prev", "view.next", "|",
    "view.zoom_out", "view.zoom_in", "view.fit", "view.actual", "|",
    "image.rot_left", "image.rot_right", "image.flip_h", "image.flip_v", "|",
    "edit.crop", "edit.draw", "edit.text", "|",
    "edit.undo", "edit.redo", "|",
    "file.save", "file.save_as", "file.compress", "|",
    "view.grid", "view.slideshow", "|",
    "tools.batch", "tools.settings",
]

CROP_RATIOS = [
    ("自由", None), ("原始比例", "orig"), ("1 : 1", 1.0), ("4 : 3", 4 / 3),
    ("3 : 4", 3 / 4), ("16 : 9", 16 / 9), ("9 : 16", 9 / 16),
]


class ElidedLabel(QLabel):
    """单行省略显示的长文本（路径），完整内容放 tooltip。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._full = ""
        self.setTextFormat(Qt.TextFormat.PlainText)

    def setFullText(self, text: str) -> None:
        self._full = text or ""
        self.setToolTip(self._full)
        self._refresh()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        fm = self.fontMetrics()
        avail = max(24, self.width() - 2)
        self.setText(fm.elidedText(self._full, Qt.TextElideMode.ElideMiddle, avail))


def list_images(folder: str) -> List[str]:
    try:
        names = os.listdir(folder)
    except OSError:
        return []
    files = [os.path.join(folder, n) for n in names
             if imageio.is_image_file(n) and os.path.isfile(os.path.join(folder, n))]
    return sort_files(files, "name_asc")


class MainWindow(QMainWindow):
    def __init__(self, start_path: Optional[str] = None) -> None:
        super().__init__()
        self.cfg = settings
        self.cache = ThumbCache(cache_dir(), self.cfg.get_int("cache/max_mb", 800) * 1024 * 1024)
        self.pool = TaskPool(4)

        self.actions = {}
        self.path: Optional[str] = None
        self.loaded = None
        self.image: Optional[QImage] = None
        self.folder = ""
        self.files: List[str] = []
        self.index = -1
        self.undo: List[QImage] = []
        self.redo: List[QImage] = []
        self.dirty = False
        self._load_gen = 0
        self._frames: List[QImage] = []
        self._frame_index = 0
        self._prev_visible = {}
        self._cache_size_done = False

        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.resize(1240, 820)
        self.setAcceptDrops(True)

        self.slide_timer = QTimer(self)
        self.slide_timer.timeout.connect(self._slide_next)
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._next_frame)

        self._build_actions()
        self._build_ui()
        self._apply_settings(initial=True)
        self._update_actions()
        self._restore_state(start_path)

    # ================================================================== 动作
    def _build_actions(self) -> None:
        handlers = {
            "file.open": self.act_open,
            "file.open_folder": self.act_open_folder,
            "file.reload": self.act_reload,
            "file.save": self.act_save,
            "file.save_as": self.act_save_as,
            "file.compress": self.act_compress,
            "file.print": self.act_print,
            "file.print_preview": self.act_print_preview,
            "file.rename": self.act_rename,
            "file.delete": self.act_delete,
            "file.copy_image": self.act_copy_image,
            "file.paste_image": self.act_paste_image,
            "file.copy_path": self.act_copy_path,
            "file.properties": self.act_properties,
            "file.quit": self.close,
            "edit.undo": self.act_undo,
            "edit.redo": self.act_redo,
            "edit.crop": self.act_crop,
            "edit.draw": self.act_draw,
            "edit.text": self.act_text,
            "edit.resize": self.act_resize,
            "edit.reset": self.act_reset,
            "view.grid": self.toggle_grid,
            "view.fullscreen": self.toggle_fullscreen,
            "view.slideshow": self.toggle_slideshow,
            "view.zoom_in": lambda: self.canvas.zoom_in(),
            "view.zoom_out": lambda: self.canvas.zoom_out(),
            "view.fit": lambda: self.canvas.fit_to_window(),
            "view.actual": lambda: self.canvas.actual_size(),
            "view.prev": lambda: self.step(-1),
            "view.next": lambda: self.step(1),
            "view.first": lambda: self.goto_index(0),
            "view.last": lambda: self.goto_index(len(self.files) - 1),
            "view.frame_prev": lambda: self.goto_frame(self._frame_index - 1),
            "view.frame_next": lambda: self.goto_frame(self._frame_index + 1),
            "view.animate": self.toggle_animation,
            "view.info": self.toggle_info_panel,
            "view.bg": self.cycle_background,
            "image.rot_left": lambda: self.rotate(-90),
            "image.rot_right": lambda: self.rotate(90),
            "image.flip_h": lambda: self.flip(True),
            "image.flip_v": lambda: self.flip(False),
            "image.rot_left_perm": lambda: self.rotate_permanent(-90),
            "image.rot_right_perm": lambda: self.rotate_permanent(90),
            "image.flip_h_perm": lambda: self.flip_permanent(True),
            "image.flip_v_perm": lambda: self.flip_permanent(False),
            "tools.batch": self.act_batch,
            "tools.settings": self.act_settings,
            "tools.clear_cache": self.act_clear_cache,
            "tools.open_cache": lambda: util.open_folder(self.cache.dir),
            "tools.wallpaper": self.act_wallpaper,
            "tools.reveal": self.act_reveal,
            "help.shortcuts": self.act_shortcuts,
            "help.about": self.act_about,
        }
        for a in ACTIONS:
            act = QAction(icons.icon(a.icon), a.text, self)
            act.setData(a.id)
            h = handlers.get(a.id)
            if h is not None:
                act.triggered.connect(h)
            self.actions[a.id] = act

    def _apply_shortcuts(self) -> None:
        for a in ACTIONS:
            act = self.actions[a.id]
            seq = self.cfg.shortcut(a.id)
            act.setShortcut(QKeySequence(seq) if seq else QKeySequence())
            act.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            tip = a.tip or a.text
            if seq:
                tip = f"{tip}\n{seq}" if tip else seq
            act.setToolTip(tip)
            act.setStatusTip(a.text)

    # ================================================================== 界面
    def _build_ui(self) -> None:
        self.canvas = ImageCanvas()
        self.canvas.zoomChanged.connect(self._on_zoom)
        self.canvas.cursorMoved.connect(self._on_cursor)
        self.canvas.editCommitted.connect(self._on_edit)
        self.canvas.toolChanged.connect(self._on_tool_changed)
        self.canvas.doubleClicked.connect(self.toggle_fullscreen)

        self.grid_page = GridPage(self.cache, self.cfg.get_int("general/thumb_size", 172),
                                  self.cfg.get("general/sort", "name_asc"))
        self.grid_page.openRequested.connect(self._open_from_grid)
        self.grid_page.contextRequested.connect(self._grid_context)
        self.grid_page.selectionCountChanged.connect(lambda _n: self._update_status())

        self.stack = QStackedWidget()
        self.stack.addWidget(self.canvas)
        self.stack.addWidget(self.grid_page)

        # 左侧目录树
        self.fs_model = QFileSystemModel(self)
        self.fs_model.setRootPath("")
        self.fs_model.setFilter(QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot
                                | QDir.Filter.Drives)
        self.tree = QTreeView()
        self.tree.setModel(self.fs_model)
        self.tree.setRootIndex(self.fs_model.index(""))
        self.tree.setHeaderHidden(True)
        for i in range(1, 4):
            self.tree.hideColumn(i)
        self.tree.clicked.connect(self._on_tree_click)
        self.tree.setMinimumWidth(170)
        self.tree.setMaximumWidth(320)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(8, 8, 0, 8)
        lv.setSpacing(6)
        title = QLabel("文件夹")
        title.setObjectName("subtitle")
        lv.addWidget(title)
        lv.addWidget(self.tree, 1)
        left.setMaximumWidth(330)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(left)
        self.splitter.addWidget(self.stack)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([210, 1000])
        self.setCentralWidget(self.splitter)

        self._build_toolbars()
        self._build_menus()
        self._build_info_dock()
        self._build_statusbar()
        self._build_tools_bar()

        self._update_title()

    def _build_toolbars(self) -> None:
        tb = QToolBar("主工具栏")
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)
        self.main_toolbar = tb

        for item in TOOLBAR_ITEMS:
            if item == "|":
                tb.addSeparator()
            elif item == "zoom":
                continue
            else:
                act = self.actions[item]
                btn = QToolButton()
                btn.setDefaultAction(act)
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
                btn.setIconSize(QSize(20, 20))
                tb.addWidget(btn)
            if item == "view.actual":
                self.zoom_label = QLabel(" 100% ")
                self.zoom_label.setMinimumWidth(52)
                self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.zoom_label.setStyleSheet("color:#4a5160;")
                tb.addWidget(self.zoom_label)

    def _build_menus(self) -> None:
        mb = self.menuBar()
        for cat in MENU_ORDER:
            menu = mb.addMenu(cat)
            for aid in MENU_LAYOUT.get(cat, []):
                if aid == "-":
                    menu.addSeparator()
                else:
                    menu.addAction(self.actions[aid])
            if cat == "图片":
                menu.addSeparator()
                perm = menu.addMenu("旋转 / 翻转并写入文件")
                for aid in ("image.rot_left_perm", "image.rot_right_perm",
                            "image.flip_h_perm", "image.flip_v_perm"):
                    perm.addAction(self.actions[aid])

    def _build_info_dock(self) -> None:
        self.dock = QDockWidget("图片信息", self)
        self.dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea
                                  | Qt.DockWidgetArea.LeftDockWidgetArea)
        self.dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable
                              | QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.dock.setMinimumWidth(252)

        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(10)

        self.info_thumb = QLabel()
        self.info_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_thumb.setMinimumHeight(120)
        self.info_thumb.setStyleSheet(
            "background:#f2f4f7;border:1px solid #e4e7ec;border-radius:8px;color:#9aa0a8;")
        self.info_thumb.setText("暂无图片")
        v.addWidget(self.info_thumb)

        self.info_name = QLabel("未打开图片")
        self.info_name.setWordWrap(True)
        self.info_name.setMinimumWidth(0)
        self.info_name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.info_name.setStyleSheet("font-weight:600;font-size:14px;")
        v.addWidget(self.info_name)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color:#e4e7ec;")
        v.addWidget(line)

        self.info_form = QFormLayout()
        self.info_form.setSpacing(7)
        self.info_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.info_values = {}
        for key in ("尺寸", "格式", "文件大小", "修改时间", "色彩模式"):
            lab = QLabel("—")
            lab.setWordWrap(True)
            lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.info_values[key] = lab
            self.info_form.addRow(f"<span style='color:#7b8290'>{key}</span>", lab)
        v.addLayout(self.info_form)

        self.exif_box = QFrame()
        self.exif_layout = QFormLayout(self.exif_box)
        self.exif_layout.setContentsMargins(0, 6, 0, 0)
        self.exif_layout.setSpacing(6)
        v.addWidget(self.exif_box)
        v.addStretch(1)

        self.info_path = ElidedLabel()
        self.info_path.setObjectName("subtitle")
        self.info_path.setMinimumWidth(0)
        self.info_path.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        v.addWidget(self.info_path)

        body.setMinimumWidth(244)
        self.dock.setWidget(body)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)

    def _build_statusbar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)
        self.lbl_path = QLabel("就绪")
        self.lbl_path.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.lbl_dims = QLabel("")
        self.lbl_zoom = QLabel("")
        self.lbl_pos = QLabel("")
        for w in (self.lbl_path, self.lbl_dims, self.lbl_zoom, self.lbl_pos):
            sb.addPermanentWidget(w) if w is not self.lbl_path else sb.addWidget(w, 1)

    def _build_tools_bar(self) -> None:
        self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)
        bar = QToolBar("工具选项")
        bar.setMovable(False)
        bar.setIconSize(QSize(18, 18))
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, bar)
        bar.setVisible(False)
        self.tools_bar = bar

        # 裁剪
        self.crop_widget = QWidget()
        h = QHBoxLayout(self.crop_widget)
        h.setContentsMargins(6, 2, 6, 2)
        h.setSpacing(8)
        h.addWidget(QLabel("比例"))
        self.ratio_box = QComboBox()
        for label, val in CROP_RATIOS:
            self.ratio_box.addItem(label, val if val is not None else -1)
        self.ratio_box.currentIndexChanged.connect(self._on_ratio)
        h.addWidget(self.ratio_box)
        h.addWidget(QLabel("拖动选区调整范围，Enter 确认，Esc 取消，空格全选"))
        h.addStretch(1)
        ok_crop = QPushButton("裁剪")
        ok_crop.setDefault(True)
        ok_crop.clicked.connect(lambda: self.canvas.apply_crop())
        h.addWidget(ok_crop)
        cancel_crop = QPushButton("取消")
        cancel_crop.clicked.connect(self.canvas.cancel_tool)
        h.addWidget(cancel_crop)
        self.crop_action = bar.addWidget(self.crop_widget)

        # 涂鸦
        self.draw_widget = QWidget()
        h2 = QHBoxLayout(self.draw_widget)
        h2.setContentsMargins(6, 2, 6, 2)
        h2.setSpacing(8)
        h2.addWidget(QLabel("画笔颜色"))
        self.brush_color_btn = ColorButton(QColor("#ff3b30"))
        self.brush_color_btn.clicked.connect(self._on_brush_color)
        h2.addWidget(self.brush_color_btn)
        h2.addWidget(QLabel("粗细"))
        self.brush_width = QSlider(Qt.Orientation.Horizontal)
        self.brush_width.setRange(1, 60)
        self.brush_width.setValue(6)
        self.brush_width.setFixedWidth(140)
        self.brush_width.valueChanged.connect(self._on_brush_width)
        h2.addWidget(self.brush_width)
        self.brush_val = QLabel("6 px")
        h2.addWidget(self.brush_val)
        h2.addStretch(1)
        done = QPushButton("完成")
        done.clicked.connect(lambda: self.canvas.cancel_tool())
        h2.addWidget(done)
        self.draw_action = bar.addWidget(self.draw_widget)

        # 文字
        self.text_widget = QWidget()
        h3 = QHBoxLayout(self.text_widget)
        h3.setContentsMargins(6, 2, 6, 2)
        h3.setSpacing(8)
        lbl = QLabel("拖动文字调整位置，Enter 确认，Esc 取消")
        h3.addWidget(lbl)
        h3.addStretch(1)
        ok_text = QPushButton("放置文字")
        ok_text.setDefault(True)
        ok_text.clicked.connect(lambda: self.canvas.commit_text())
        h3.addWidget(ok_text)
        cancel_text = QPushButton("取消")
        cancel_text.clicked.connect(self.canvas.cancel_tool)
        h3.addWidget(cancel_text)
        self.text_action = bar.addWidget(self.text_widget)

        for a in (self.crop_action, self.draw_action, self.text_action):
            a.setVisible(False)

    # ================================================================== 设置
    def _apply_settings(self, initial: bool = False) -> None:
        self._apply_shortcuts()
        self.canvas.set_background(CANVAS_COLORS.get(
            self.cfg.get("view/canvas_bg", "dark"), CANVAS_COLORS["dark"]))
        self.canvas.set_checkerboard(self.cfg.get_bool("view/checkerboard", True))
        self.slide_timer.setInterval(max(1, self.cfg.get_int("general/slideshow_interval", 3)) * 1000)
        self.grid_page.size_slider.blockSignals(True)
        self.grid_page.size_slider.setValue(self.cfg.get_int("general/thumb_size", 172))
        self.grid_page.size_slider.blockSignals(False)
        self.grid_page.set_sort(self.cfg.get("general/sort", "name_asc"))
        self.actions["view.info"].setCheckable(True)
        self.actions["view.info"].setChecked(self.dock.isVisible())

    # ================================================================== 启动
    def _restore_state(self, start_path: Optional[str]) -> None:
        geo = self.cfg.q.value("window/geometry")
        if geo:
            try:
                self.restoreGeometry(geo)
            except Exception:
                pass

        if start_path:
            if os.path.isdir(start_path):
                self.open_folder(start_path, switch_grid=False)
            elif os.path.isfile(start_path):
                self.open_path(start_path)
            return

        folder = ""
        if self.cfg.get_bool("general/open_last", True):
            last = self.cfg.get("general/last_folder", "")
            if last and os.path.isdir(last):
                folder = last
        if not folder:
            pics = os.path.join(os.path.expanduser("~"), "Pictures")
            if os.path.isdir(pics):
                folder = pics
        if folder:
            self.open_folder(folder, switch_grid=False)
        self.cache.prune_async()

    # ================================================================== 文件夹与加载
    def open_folder(self, folder: str, switch_grid: bool = False, select: str = "") -> None:
        if not folder or not os.path.isdir(folder):
            return
        folder = os.path.abspath(folder)
        self.folder = folder
        self.files = list_images(folder)
        self.grid_page.set_folder(folder, self.files)
        self.cfg.set("general/last_folder", folder)
        self.cfg.push_recent("folders", folder)
        self._sync_tree(folder)
        if select:
            self.path = select
            self.index = self._index_of(select)
        if switch_grid:
            self.stack.setCurrentWidget(self.grid_page)
            self.actions["view.grid"].setChecked(True)
            self._update_status()
            self._update_actions()
            return
        if self.files:
            target = select if select in self.files else (
                self.path if self.path in self.files else self.files[0])
            self.open_path(target)
        else:
            self.path = None
            self.index = -1
            self._show_empty("这个文件夹里没有可显示的图片")
        self._update_actions()

    def open_path(self, path: str, skip_confirm: bool = False) -> None:
        if not path:
            return
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            self._toast("文件不存在：" + path)
            return
        if not skip_confirm and self.dirty and not self._confirm_discard():
            return
        folder = os.path.dirname(path)
        if os.path.normcase(folder) != os.path.normcase(self.folder):
            self.folder = folder
            self.files = list_images(folder)
            self.grid_page.set_folder(folder, self.files)
            self.cfg.set("general/last_folder", folder)
            self.cfg.push_recent("folders", folder)
            self._sync_tree(folder)
        if path not in self.files:
            self.files = list_images(folder)
            self.grid_page.set_folder(folder, self.files)
        self.path = path
        self.index = self._index_of(path)
        self.stack.setCurrentWidget(self.canvas)
        self.actions["view.grid"].setChecked(False)
        self._load(path)

    def _load(self, path: str) -> None:
        self._load_gen += 1
        gen = self._load_gen
        self._toast("正在打开 " + os.path.basename(path))
        task = LoadTask(path, gen)
        task.signals.result.connect(self._on_loaded)
        task.signals.error.connect(lambda e: self._toast("打开失败：" + e))
        self.pool.start(task)

    def _on_loaded(self, payload) -> None:
        gen, loaded = payload
        if gen != self._load_gen:
            return
        if loaded.image is None:
            QMessageBox.warning(self, "无法打开", loaded.error or "未知错误")
            self._toast("打开失败")
            return
        self.loaded = loaded
        self.image = loaded.image
        self.undo.clear()
        self.redo.clear()
        self.dirty = False
        self._frames = list(loaded.frames) if loaded.frames else []
        self._frame_index = 0
        self.canvas.clear_view_transform()
        self.canvas.set_image(self.image, fit=True)
        self._update_info()
        self._update_status()
        self._update_title()
        self._update_actions()
        self.cfg.push_recent("files", loaded.path)
        if self.folder and loaded.path in self.files:
            self.grid_page.select_path(loaded.path)
        self._toast(os.path.basename(loaded.path))

    def _show_empty(self, text: str) -> None:
        self.loaded = None
        self.image = None
        self.canvas.set_image(None)
        self.info_name.setText(text)
        self.info_thumb.setPixmap(QPixmap())
        self.info_thumb.setText("暂无图片")
        for lab in self.info_values.values():
            lab.setText("—")
        while self.exif_layout.rowCount():
            self.exif_layout.removeRow(0)
        self.lbl_dims.setText("")
        self.lbl_zoom.setText("")
        self.lbl_path.setText(text)
        self._update_title()

    def _sync_tree(self, folder: str) -> None:
        idx = self.fs_model.index(folder)
        if idx.isValid():
            self.tree.setCurrentIndex(idx)
            self.tree.expand(idx.parent())
            self.tree.scrollTo(idx, QTreeView.ScrollHint.EnsureVisible)

    def _index_of(self, path: str) -> int:
        try:
            return self.files.index(path)
        except ValueError:
            return -1

    # ================================================================== 导航
    def step(self, delta: int) -> None:
        if not self.files:
            return
        if self.index < 0:
            self.open_path(self.files[0])
            return
        n = len(self.files)
        new = self.index + delta
        if 0 <= new < n:
            self.open_path(self.files[new])
        elif self.cfg.get_bool("general/loop", True):
            self.open_path(self.files[new % n])

    def goto_index(self, i: int) -> None:
        if 0 <= i < len(self.files):
            self.open_path(self.files[i])

    def goto_frame(self, i: int) -> None:
        if not self._frames:
            return
        i %= len(self._frames)
        self._frame_index = i
        self.canvas.set_image(self._frames[i])
        self._update_status()

    def _next_frame(self) -> None:
        if len(self._frames) > 1:
            self.goto_frame(self._frame_index + 1)

    def toggle_animation(self) -> None:
        if self.anim_timer.isActive():
            self.anim_timer.stop()
            self._toast("已暂停动画")
        elif len(self._frames) > 1:
            self.anim_timer.start(100)
            self._toast("正在播放动画")

    # ================================================================== 视图
    def toggle_grid(self) -> None:
        if self.stack.currentWidget() is self.grid_page:
            self.stack.setCurrentWidget(self.canvas)
            self.actions["view.grid"].setChecked(False)
            if not self.image and self.path:
                self._load(self.path)
        else:
            if not self.files:
                self.act_open_folder()
                return
            self.stack.setCurrentWidget(self.grid_page)
            self.actions["view.grid"].setChecked(True)
            if self.path:
                self.grid_page.select_path(self.path)
        self._update_status()
        self._update_actions()

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            for w, vis in self._prev_visible.items():
                w.setVisible(vis)
            self._prev_visible.clear()
        else:
            self._prev_visible = {
                self.main_toolbar: self.main_toolbar.isVisible(),
                self.tools_bar: self.tools_bar.isVisible(),
                self.dock: self.dock.isVisible(),
                self.statusBar(): self.statusBar().isVisible(),
                self.menuBar(): self.menuBar().isVisible(),
                self.splitter.widget(0): self.splitter.widget(0).isVisible(),
            }
            self.showFullScreen()
            self.main_toolbar.hide()
            self.tools_bar.hide()
            self.dock.hide()
            self.statusBar().hide()
            self.menuBar().hide()
            self.splitter.widget(0).hide()
        self.actions["view.fullscreen"].setChecked(self.isFullScreen())

    def toggle_slideshow(self) -> None:
        if self.slide_timer.isActive():
            self.slide_timer.stop()
            self.actions["view.slideshow"].setChecked(False)
            if self.isFullScreen():
                self.toggle_fullscreen()
            self._toast("幻灯片已停止")
            return
        if not self.files:
            return
        self.actions["view.slideshow"].setChecked(True)
        if not self.isFullScreen():
            self.toggle_fullscreen()
        self.slide_timer.start()
        self._toast("幻灯片播放中，按 Esc 退出")

    def _slide_next(self) -> None:
        if not self.files:
            self.slide_timer.stop()
            return
        if self.index < 0:
            self.goto_index(0)
            return
        nxt = self.index + 1
        if nxt >= len(self.files):
            if self.cfg.get_bool("general/loop", True):
                nxt = 0
            else:
                self.toggle_slideshow()
                return
        self.open_path(self.files[nxt], skip_confirm=True)

    def toggle_info_panel(self) -> None:
        vis = not self.dock.isVisible()
        self.dock.setVisible(vis)
        self.actions["view.info"].setChecked(vis)

    def cycle_background(self) -> None:
        order = ["dark", "mid", "light"]
        cur = self.cfg.get("view/canvas_bg", "dark")
        nxt = order[(order.index(cur) + 1) % len(order)] if cur in order else "dark"
        self.cfg.set("view/canvas_bg", nxt)
        self.canvas.set_background(CANVAS_COLORS[nxt])
        self._toast({"dark": "深灰背景", "mid": "中灰背景", "light": "浅色背景"}[nxt])

    # ================================================================== 变换
    def rotate(self, delta: int) -> None:
        if not self.image:
            return
        self.canvas.rotate_by(delta)
        self.dirty = True
        self._update_title()
        self._update_status()

    def flip(self, horizontal: bool) -> None:
        if not self.image:
            return
        self.canvas.flip(horizontal)
        self.dirty = True
        self._update_title()

    def rotate_permanent(self, delta: int) -> None:
        if not self.image:
            return
        self.canvas.rotate_by(delta)
        self.canvas.bake_transform()
        self.act_save()

    def flip_permanent(self, horizontal: bool) -> None:
        if not self.image:
            return
        self.canvas.flip(horizontal)
        self.canvas.bake_transform()
        self.act_save()

    # ================================================================== 编辑提交
    def _trim_undo(self) -> None:
        """限制撤销栈的步数与显存占用（大图很吃内存）。"""
        MAX_STEPS, MAX_PIXELS = 15, 120_000_000
        while len(self.undo) > MAX_STEPS:
            self.undo.pop(0)
        total = sum(im.width() * im.height() for im in self.undo if im is not None)
        while len(self.undo) > 1 and total > MAX_PIXELS:
            d = self.undo.pop(0)
            if d is not None:
                total -= d.width() * d.height()

    def _on_edit(self, before: QImage, after: QImage) -> None:
        self.undo.append(before)
        self._trim_undo()
        self.redo.clear()
        self.image = after
        self.dirty = True
        self._update_title()
        self._update_status()
        self._update_info()
        self._update_actions()

    def _push_image(self, img: QImage) -> None:
        if self.image is not None:
            self.undo.append(self.image)
            self._trim_undo()
        self.redo.clear()
        self.image = img
        self.canvas.set_image(img)
        self.dirty = True
        self._update_title()
        self._update_info()
        self._update_actions()

    def act_undo(self) -> None:
        if not self.undo:
            return
        self.redo.append(self.image)
        self.image = self.undo.pop()
        self.canvas.clear_view_transform()
        self.canvas.set_image(self.image)
        self.dirty = True
        self._update_title()
        self._update_status()
        self._update_info()
        self._update_actions()

    def act_redo(self) -> None:
        if not self.redo:
            return
        self.undo.append(self.image)
        self.image = self.redo.pop()
        self.canvas.clear_view_transform()
        self.canvas.set_image(self.image)
        self.dirty = True
        self._update_title()
        self._update_status()
        self._update_info()
        self._update_actions()

    def act_crop(self) -> None:
        if not self.image:
            return
        if self.canvas.mode == MODE_CROP:
            self.canvas.apply_crop()
            return
        self.canvas.begin_crop(None)
        self.ratio_box.setCurrentIndex(0)

    def act_draw(self) -> None:
        if not self.image:
            return
        self.canvas.begin_draw()
        self._on_brush_color()

    def act_text(self) -> None:
        if not self.image:
            return
        dlg = TextDialog(self)
        if dlg.exec() == TextDialog.DialogCode.Accepted:
            v = dlg.values()
            self.canvas.begin_text(v["text"], v["font"], v["color"], v["outline"])

    def act_resize(self) -> None:
        if not self.image:
            return
        dlg = ResizeDialog(self.image.width(), self.image.height(), self)
        if dlg.exec() == ResizeDialog.DialogCode.Accepted:
            w, h = dlg.result_size
            if (w, h) == (self.image.width(), self.image.height()):
                return
            new = imageio.resize_qimage(self.image, w, h)
            self._push_image(new)
            self.canvas.fit_to_window()
            self._toast(f"尺寸已调整为 {w} × {h}")

    def act_reset(self) -> None:
        if not self.path:
            return
        if not (self.undo or self.redo or self.dirty or self.canvas.has_view_transform()):
            return
        if QMessageBox.question(self, "放弃修改", "确定放弃所有修改，回到磁盘上的原图吗？") \
                != QMessageBox.StandardButton.Yes:
            return
        self.dirty = False
        self.canvas.clear_view_transform()
        self._load(self.path)

    def _on_ratio(self, index: int) -> None:
        val = self.ratio_box.itemData(index)
        if val == -1:
            self.canvas.set_crop_ratio(None)
        elif val == "orig":
            if self.image:
                self.canvas.set_crop_ratio(self.image.width() / max(1, self.image.height()))
        else:
            self.canvas.set_crop_ratio(float(val))

    def _on_brush_color(self) -> None:
        self.canvas.brush_color = self.brush_color_btn.color()

    def _on_brush_width(self, v: int) -> None:
        self.canvas.brush_width = v
        self.brush_val.setText(f"{v} px")

    def _on_tool_changed(self, mode: str) -> None:
        for act in (self.crop_action, self.draw_action, self.text_action):
            act.setVisible(False)
        if mode == MODE_CROP:
            self.crop_action.setVisible(True)
            self.tools_bar.setVisible(True)
        elif mode == MODE_DRAW:
            self.draw_action.setVisible(True)
            self.tools_bar.setVisible(True)
        elif mode == MODE_TEXT:
            self.text_action.setVisible(True)
            self.tools_bar.setVisible(True)
        else:
            self.tools_bar.setVisible(False)
        self._update_actions()

    # ================================================================== 文件操作
    def act_open(self) -> None:
        exts = " ".join("*" + e for e in imageio.READABLE_EXTS)
        paths, _ = QFileDialog.getOpenFileNames(
            self, "打开图片", self.folder or "",
            f"图片文件 ({exts});;所有文件 (*.*)")
        if paths:
            if len(paths) > 1:
                self.open_path(paths[0])
                self._toast(f"已打开 {os.path.basename(paths[0])}，同文件夹共 {len(self.files)} 张")
            else:
                self.open_path(paths[0])

    def act_open_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "打开文件夹", self.folder or "")
        if folder:
            self.open_folder(folder, switch_grid=True)

    def act_reload(self) -> None:
        if self.path:
            self.dirty = False
            self.canvas.clear_view_transform()
            self._load(self.path)

    def _current_fmt(self) -> str:
        if self.loaded and self.loaded.fmt in imageio.FORMAT_BY_KEY:
            return self.loaded.fmt
        if self.path:
            ext = os.path.splitext(self.path)[1].lower()
            if ext in (".jpg", ".jpeg", ".jpe", ".jfif"):
                return "JPEG"
            if ext in (".tif", ".tiff"):
                return "TIFF"
        return "PNG"

    def _bake_if_needed(self) -> None:
        if self.canvas.has_view_transform():
            self.canvas.bake_transform()

    def act_save(self) -> None:
        if not self.image or not self.path:
            if self.image and not self.path:
                self.act_save_as()
            return
        self._bake_if_needed()
        fmt = self._current_fmt()
        if fmt not in imageio.FORMAT_BY_KEY:
            self.act_save_as()
            return
        if len(self._frames) > 1:
            if QMessageBox.question(
                    self, "多帧图片",
                    f"这是包含 {len(self._frames)} 帧的图片（动图 / 多页 TIFF），\n"
                    "保存后只会保留当前这一帧，其余帧将丢失。\n\n确定继续吗？") \
                    != QMessageBox.StandardButton.Yes:
                return
        if self.cfg.get_bool("general/backup_before_overwrite", True):
            try:
                bdir = os.path.join(os.path.dirname(self.path), ".picsprite_backup")
                os.makedirs(bdir, exist_ok=True)
                shutil.copy2(self.path, os.path.join(bdir, os.path.basename(self.path)))
            except Exception:
                pass
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            size = imageio.save_qimage(self.image, self.path, fmt, 92, True,
                                       self.loaded.exif_bytes if self.loaded else None,
                                       self.loaded.icc if self.loaded else None)
        except Exception as e:                        # noqa: BLE001
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "保存失败", str(e))
            return
        QApplication.restoreOverrideCursor()
        self.dirty = False
        self._update_title()
        self._toast(f"已保存 · {util.human_size(size)}")
        self._refresh_after_write()

    def act_save_as(self) -> None:
        if not self.image:
            return
        self._bake_if_needed()
        dlg = SaveAsDialog(self.path or "", self.image,
                           self.loaded.exif_bytes if self.loaded else None,
                           self.loaded.icc if self.loaded else None,
                           self._current_fmt(), self)
        if dlg.exec() != SaveAsDialog.DialogCode.Accepted:
            return
        p = dlg.params
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            size, w, h, q = imageio.save_with_options(
                self.image, p["path"], p["fmt"], p["quality"], p["resize"],
                p["target_bytes"], p["keep_exif"],
                self.loaded.exif_bytes if self.loaded else None,
                self.loaded.icc if self.loaded else None)
        except Exception as e:                        # noqa: BLE001
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "保存失败", str(e))
            return
        QApplication.restoreOverrideCursor()

        same = os.path.normcase(os.path.abspath(p["path"])) == \
            os.path.normcase(os.path.abspath(self.path or ""))
        if same:
            self.dirty = False
            self._update_title()
        self._toast(f"已保存 {os.path.basename(p['path'])} · {util.human_size(size)} · {w}×{h}")
        self._refresh_after_write()
        if not same:
            ret = QMessageBox.question(
                self, "保存完成",
                f"已保存为：\n{p['path']}\n\n体积 {util.human_size(size)}，尺寸 {w} × {h}\n\n"
                "是否打开这个新文件？")
            if ret == QMessageBox.StandardButton.Yes:
                self.dirty = False
                self.open_path(p["path"])

    def act_compress(self) -> None:
        if not self.image or not self.path:
            self._toast("请先打开一张图片")
            return
        self._bake_if_needed()
        dlg = CompressDialog(self.path, self.image,
                             self.loaded.exif_bytes if self.loaded else None, self)
        if dlg.exec() == CompressDialog.DialogCode.Accepted and dlg.saved_path:
            self._refresh_after_write()
            if os.path.normcase(dlg.saved_path) == os.path.normcase(self.path):
                self.dirty = False
                self._load(self.path)

    # ================================================================== 打印
    def _print_options(self) -> PrintOptions:
        o = PrintOptions()
        o.per_page = max(1, self.cfg.get_int("print/per_page", 1))
        o.scale = str(self.cfg.get("print/scale", "fit") or "fit")
        if o.scale not in ("fit", "shrink", "fill"):
            o.scale = "fit"
        try:
            o.margin_mm = float(self.cfg.get("print/margin_mm", 6.0))
        except (TypeError, ValueError):
            o.margin_mm = 6.0
        try:
            o.gap_mm = float(self.cfg.get("print/gap_mm", 4.0))
        except (TypeError, ValueError):
            o.gap_mm = 4.0
        o.show_title = self.cfg.get_bool("print/show_title", True)
        o.show_date = self.cfg.get_bool("print/show_date", False)
        return o

    def _save_print_options(self, o: PrintOptions) -> None:
        self.cfg.set("print/per_page", o.per_page)
        self.cfg.set("print/scale", o.scale)
        self.cfg.set("print/margin_mm", round(o.margin_mm, 1))
        self.cfg.set("print/gap_mm", round(o.gap_mm, 1))
        self.cfg.set("print/show_title", o.show_title)
        self.cfg.set("print/show_date", o.show_date)

    @staticmethod
    def _print_date(loaded) -> str:
        if loaded is None:
            return ""
        for key in ("拍摄时间", "拍摄日期", "DateTimeOriginal", "创建日期"):
            v = (loaded.exif or {}).get(key)
            if v:
                return str(v)
        if loaded.mtime:
            return datetime.datetime.fromtimestamp(loaded.mtime).strftime("%Y-%m-%d")
        return ""

    @staticmethod
    def _print_max_side(count: int) -> int:
        """按张数控制内存：张数越多，单张解码得越小。"""
        if count > 30:
            return 1600
        if count > 12:
            return 2200
        return 4200

    def _print_item_from_current(self) -> List[PrintItem]:
        if self.image is None:
            return []
        img = self.image
        side = max(img.width(), img.height())
        limit = 4200
        if side > limit:
            img = img.scaled(int(img.width() * limit / side), int(img.height() * limit / side),
                             Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        title = os.path.basename(self.path) if self.path else "剪贴板图片"
        return [PrintItem(img, title, self._print_date(self.loaded))]

    def _print_items_from_paths(self, paths: List[str], limit: int) -> List[PrintItem]:
        paths = [p for p in paths if p][:limit]
        max_side = self._print_max_side(len(paths))
        items: List[PrintItem] = []
        for path in paths:
            loaded = imageio.load_image(path, max_frames=1)
            img = loaded.image
            if img is None:
                continue
            side = max(img.width(), img.height())
            if side > max_side:
                img = img.scaled(int(img.width() * max_side / side),
                                 int(img.height() * max_side / side),
                                 Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            items.append(PrintItem(img, os.path.basename(path), self._print_date(loaded)))
        return items

    def _print_scopes(self):
        """返回 [(键, 文字, 取数据函数)]，按当前界面状态动态给出可打印范围。"""
        scopes = []
        in_grid = self.stack.currentWidget() is self.grid_page
        picked = self.grid_page.selected_paths() if in_grid else []

        if self.image is not None:
            scopes.append(("current", "当前图片", self._print_item_from_current))
        if picked and len(picked) > 1:
            scopes.append(("selected",
                           f"选中的 {len(picked)} 张图片",
                           lambda p=list(picked): self._print_items_from_paths(p, 100)))
        if self.files and len(self.files) > 1:
            n = min(len(self.files), 50)
            label = f"整个文件夹（{len(self.files)} 张）" if len(self.files) <= 50 \
                else f"整个文件夹（前 50 张，共 {len(self.files)} 张）"
            scopes.append(("folder", label,
                           lambda f=list(self.files): self._print_items_from_paths(f, 50)))
        return scopes

    def _make_printer(self, opts: PrintOptions):
        from PySide6.QtPrintSupport import QPrinter
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printing.apply_margins(printer, opts.margin_mm)
        return printer

    def act_print(self) -> None:
        scopes = self._print_scopes()
        if not scopes:
            self._toast("请先打开一张图片")
            return
        self._bake_if_needed()          # 打印所见即所得：先把临时旋转/翻转落到像素上
        opts = self._print_options()
        printer = self._make_printer(opts)
        if not printer.isValid():
            # 没有打印机也让对话框开着：用户可以在这里「导出为 PDF」
            QMessageBox.warning(
                self, "没有可用的打印机",
                "没有找到可用的打印机。\n\n"
                "你可以点「打印机设置」换一台打印机，"
                "或者直接用「导出为 PDF」保存成文件。")
        dlg = PrintDialog(printer, scopes, opts, self)
        if dlg.exec() != PrintDialog.DialogCode.Accepted:
            self._save_print_options(dlg.opts)
            return
        self._save_print_options(dlg.opts)
        items = dlg.items
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            pages = printing.draw_document(printer, items, dlg.opts)
        except Exception as exc:                              # noqa: BLE001
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "打印失败", str(exc))
            return
        QApplication.restoreOverrideCursor()
        self._toast(f"已发送到打印机 · {len(items)} 张 / {pages} 页")

    def act_print_preview(self) -> None:
        from PySide6.QtPrintSupport import QPrintPreviewDialog
        scopes = self._print_scopes()
        if not scopes:
            self._toast("请先打开一张图片")
            return
        self._bake_if_needed()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            items = scopes[0][2]()
        finally:
            QApplication.restoreOverrideCursor()
        if not items:
            self._toast("没有可打印的图片")
            return
        opts = self._print_options()
        printer = self._make_printer(opts)
        dlg = QPrintPreviewDialog(printer, self)
        dlg.setWindowTitle("打印预览")
        dlg.resize(1020, 780)
        dlg.paintRequested.connect(
            lambda pr: printing.draw_document(pr, items, opts))
        dlg.exec()

    def _refresh_after_write(self) -> None:
        self.files = list_images(self.folder) if self.folder else []
        self.grid_page.set_folder(self.folder, self.files)
        if self.path:
            self.index = self._index_of(self.path)
            self.grid_page.select_path(self.path)
        self._update_status()
        if self.loaded and self.path and os.path.exists(self.path):
            try:
                st = os.stat(self.path)
                self.loaded.file_size = st.st_size
                self.loaded.mtime = st.st_mtime
            except OSError:
                pass
            self._update_info()

    def act_rename(self) -> None:
        if not self.path:
            return
        old = os.path.basename(self.path)
        new, ok = QInputDialog.getText(self, "重命名", "新的文件名：", text=old)
        if not ok or not new.strip() or new.strip() == old:
            return
        new = new.strip()
        folder = os.path.dirname(self.path)
        dst = os.path.join(folder, new)
        if os.path.exists(dst):
            QMessageBox.warning(self, "重命名失败", "目标文件名已存在")
            return
        try:
            os.rename(self.path, dst)
        except OSError as e:
            QMessageBox.warning(self, "重命名失败", str(e))
            return
        self.path = dst
        self.dirty = False
        self.files = list_images(folder)
        self.grid_page.set_folder(folder, self.files)
        self.index = self._index_of(dst)
        if self.loaded:
            self.loaded.path = dst
        self._update_info()
        self._update_status()
        self._update_title()
        self._toast("已重命名为 " + new)

    def act_delete(self) -> None:
        if not self.path:
            return
        if self.cfg.get_bool("general/confirm_delete", True):
            ret = QMessageBox.question(
                self, "删除文件",
                f"确定把「{os.path.basename(self.path)}」放入回收站吗？")
            if ret != QMessageBox.StandardButton.Yes:
                return
        target = self.path
        ok = util.recycle(target)
        if not ok:
            QMessageBox.warning(self, "删除失败", "无法删除该文件")
            return
        idx = self.index
        self.dirty = False
        self.path = None
        self.files = list_images(self.folder)
        self.grid_page.set_folder(self.folder, self.files)
        if self.files:
            self.open_path(self.files[min(idx, len(self.files) - 1)])
        else:
            self._show_empty("文件夹已空")
        self._toast("已放入回收站")

    def act_copy_image(self) -> None:
        if not self.image:
            return
        self._bake_if_needed()
        QApplication.clipboard().setImage(self.image)
        self._toast("图片已复制到剪贴板")

    def act_paste_image(self) -> None:
        img = QApplication.clipboard().image()
        if img.isNull():
            self._toast("剪贴板里没有图片")
            return
        if self.dirty and not self._confirm_discard():
            return
        self.loaded = imageio.LoadedImage(path="", image=img, fmt="PNG", mode="RGBA")
        self.image = img
        self.path = None
        self.index = -1
        self.undo.clear()
        self.redo.clear()
        self.dirty = True
        self.canvas.clear_view_transform()
        self.canvas.set_image(img, fit=True)
        self.stack.setCurrentWidget(self.canvas)
        self.info_name.setText("剪贴板图片")
        self.info_thumb.setText("来自剪贴板")
        for k in self.info_values:
            self.info_values[k].setText("—")
        self.info_values["尺寸"].setText(f"{img.width()} × {img.height()}")
        self.info_values["格式"].setText("剪贴板")
        self.lbl_dims.setText(f"{img.width()} × {img.height()}")
        self._update_title()
        self._update_actions()
        self._toast("已粘贴，按 Ctrl+S 保存为新文件")

    def act_copy_path(self) -> None:
        if self.path:
            QApplication.clipboard().setText(self.path)
            self._toast("路径已复制")

    def act_properties(self) -> None:
        if not self.path or not self.loaded:
            return
        PropertiesDialog(self.path, self.loaded, self).exec()

    def act_reveal(self) -> None:
        if self.path:
            util.reveal_in_explorer(self.path)

    def act_wallpaper(self) -> None:
        if not self.image:
            return
        self._bake_if_needed()
        tmp = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")),
                           "picsprite_wallpaper.jpg")
        try:
            imageio.save_qimage(self.image, tmp, "JPEG", 95)
        except Exception as e:                        # noqa: BLE001
            QMessageBox.warning(self, "设置壁纸失败", str(e))
            return
        if util.set_wallpaper(tmp):
            self._toast("已设为桌面壁纸")
        else:
            QMessageBox.warning(self, "设置壁纸失败", "系统拒绝了壁纸设置请求")

    def act_batch(self) -> None:
        paths = self.grid_page.selected_paths() if self.stack.currentWidget() is self.grid_page else []
        if not paths:
            paths = list(self.files)
        if not paths:
            self._toast("请先打开一个文件夹")
            return
        dlg = BatchDialog(paths, self)
        dlg.finished.connect(self._after_batch)
        dlg.exec()

    def _after_batch(self) -> None:
        if not self.folder:
            return
        current = self.path
        self.files = list_images(self.folder)
        self.grid_page.set_folder(self.folder, self.files)
        if current and current in self.files:
            self.path = current
            self.index = self._index_of(current)
            self.dirty = False
            self._load(current)
        elif self.files:
            self.open_path(self.files[0], skip_confirm=True)
        self._update_status()

    def act_clear_cache(self) -> None:
        if QMessageBox.question(self, "清空缓存", "确定清空所有缩略图缓存吗？") \
                != QMessageBox.StandardButton.Yes:
            return
        self.cache.clear()
        self.grid_page.refresh()
        self._toast("缩略图缓存已清空")

    def act_settings(self) -> None:
        dlg = SettingsDialog(self.cache, self)
        dlg.applied.connect(self._on_settings_applied)
        dlg.exec()

    def _on_settings_applied(self) -> None:
        self._apply_settings()
        self.grid_page.grid.set_thumb_size(self.cfg.get_int("general/thumb_size", 172))
        self.grid_page.set_sort(self.cfg.get("general/sort", "name_asc"))
        self._toast("设置已保存")

    def act_shortcuts(self) -> None:
        ShortcutsDialog(self).exec()

    def act_about(self) -> None:
        QMessageBox.about(self, "关于 " + APP_NAME, about_text())

    # ================================================================== 状态刷新
    def _on_zoom(self, percent: float) -> None:
        text = f"{percent:.0f}%"
        self.lbl_zoom.setText(f"缩放 {text}")
        if hasattr(self, "zoom_label"):
            self.zoom_label.setText(f" {text} ")

    def _on_cursor(self, pos) -> None:
        if pos is None:
            self.lbl_pos.setText("")
        else:
            self.lbl_pos.setText(f"x {pos[0]}, y {pos[1]}")

    def _update_title(self) -> None:
        if self.path:
            name = os.path.basename(self.path)
        elif self.image is not None:
            name = "剪贴板图片"
        else:
            name = ""
        star = " *" if self.dirty else ""
        self.setWindowTitle(f"{name}{star} — {APP_NAME}" if name else APP_NAME)

    def _update_status(self) -> None:
        if self.stack.currentWidget() is self.grid_page:
            sel = len(self.grid_page.selected_paths())
            self.lbl_path.setText(self.folder or "缩略图浏览")
            self.lbl_dims.setText(f"{len(self.files)} 张")
            self.lbl_zoom.setText(f"已选 {sel} 张" if sel else "")
            self.lbl_pos.setText("")
            return
        if self.path:
            self.lbl_path.setText(self.path)
        else:
            self.lbl_path.setText("就绪")
        if self.image:
            self.lbl_dims.setText(f"{self.image.width()} × {self.image.height()}")
        else:
            self.lbl_dims.setText("")
        self._on_zoom(self.canvas.zoom() * 100)
        if len(self._frames) > 1:
            self.lbl_pos.setText(f"第 {self._frame_index + 1}/{len(self._frames)} 帧")
        elif self.files and self.index >= 0:
            self.lbl_pos.setText(f"{self.index + 1} / {len(self.files)}")
        else:
            self.lbl_pos.setText("")

    def _update_info(self) -> None:
        if not self.loaded or not self.image:
            return
        d = self.loaded
        self.info_name.setText(os.path.basename(d.path) if d.path else "剪贴板图片")
        cw = self.image.width() if self.image is not None else d.width
        chh = self.image.height() if self.image is not None else d.height
        self.info_values["尺寸"].setText(f"{cw} × {chh} 像素")
        self.info_values["格式"].setText(imageio.format_label(d.fmt or d.path))
        self.info_values["文件大小"].setText(util.human_size(d.file_size) if d.file_size else "—")
        try:
            self.info_values["修改时间"].setText(
                datetime.datetime.fromtimestamp(d.mtime).strftime("%Y-%m-%d %H:%M")
                if d.mtime else "—")
        except Exception:
            self.info_values["修改时间"].setText("—")
        self.info_values["色彩模式"].setText(d.mode or "—")

        while self.exif_layout.rowCount():
            self.exif_layout.removeRow(0)
        if d.exif:
            title = QLabel("EXIF")
            title.setStyleSheet("color:#7b8290;font-weight:600;")
            self.exif_layout.addRow(title)
            for k, v in d.exif.items():
                lab = QLabel(str(v))
                lab.setWordWrap(True)
                lab.setMinimumWidth(0)
                lab.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                self.exif_layout.addRow(f"<span style='color:#7b8290'>{k}</span>", lab)

        pm = QPixmap.fromImage(self.image)
        if not pm.isNull():
            self.info_thumb.setPixmap(pm.scaled(210, 150, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation))
        self.info_path.setFullText(os.path.dirname(d.path) if d.path else "")

    def _update_actions(self) -> None:
        has_img = self.image is not None
        in_grid = self.stack.currentWidget() is self.grid_page
        for aid in ("file.save", "file.save_as", "file.compress", "file.rename",
                    "file.delete", "file.copy_image", "file.copy_path",
                    "file.properties", "edit.crop", "edit.draw", "edit.text",
                    "edit.resize", "image.rot_left", "image.rot_right",
                    "image.flip_h", "image.flip_v", "image.rot_left_perm",
                    "image.rot_right_perm", "image.flip_h_perm", "image.flip_v_perm",
                    "tools.wallpaper", "tools.reveal", "view.zoom_in", "view.zoom_out",
                    "view.fit", "view.actual", "file.print", "file.print_preview"):
            self.actions[aid].setEnabled(has_img)
        self.actions["edit.undo"].setEnabled(bool(self.undo))
        self.actions["edit.redo"].setEnabled(bool(self.redo))
        self.actions["edit.reset"].setEnabled(has_img and (self.dirty or bool(self.undo)))
        self.actions["view.frame_prev"].setEnabled(len(self._frames) > 1)
        self.actions["view.frame_next"].setEnabled(len(self._frames) > 1)
        self.actions["view.prev"].setEnabled(bool(self.files) and not in_grid)
        self.actions["view.next"].setEnabled(bool(self.files) and not in_grid)
        self.actions["view.first"].setEnabled(bool(self.files) and not in_grid)
        self.actions["view.last"].setEnabled(bool(self.files) and not in_grid)
        self.actions["view.slideshow"].setEnabled(bool(self.files))
        self.actions["view.grid"].setCheckable(True)
        self.actions["view.slideshow"].setCheckable(True)
        self.actions["view.fullscreen"].setCheckable(True)
        self.actions["view.fullscreen"].setChecked(self.isFullScreen())
        self.actions["view.grid"].setChecked(in_grid)

    def _toast(self, text: str) -> None:
        self.statusBar().showMessage(text, 4000)

    def _confirm_discard(self) -> bool:
        """返回 True 表示可以继续（已保存或选择放弃）。"""
        ret = QMessageBox.question(
            self, "未保存的修改",
            "当前图片有未保存的修改，是否保存？",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel)
        if ret == QMessageBox.StandardButton.Save:
            self.act_save()
            return not self.dirty
        if ret == QMessageBox.StandardButton.Discard:
            return True
        return False

    # ================================================================== 右键菜单
    def _build_context_menu(self, paths: Optional[List[str]] = None) -> QMenu:
        menu = QMenu(self)
        if paths is not None:
            if len(paths) == 1:
                open_act = menu.addAction(icons.icon("image"), "打开这张图片")
                open_act.triggered.connect(lambda: self.open_path(paths[0]))
            elif len(paths) > 1:
                batch_act = menu.addAction(
                    icons.icon("batch"), f"批量处理选中的 {len(paths)} 个文件…")
                batch_act.triggered.connect(self._batch_selected)
            menu.addSeparator()

        last_cat = None
        for aid, visible in self.cfg.context_items():
            if not visible or aid not in ACTION_MAP or aid not in self.actions:
                continue
            a = ACTION_MAP[aid]
            if last_cat is not None and a.category != last_cat:
                menu.addSeparator()
            last_cat = a.category
            menu.addAction(self.actions[aid])
        return menu

    def _batch_selected(self) -> None:
        paths = self.grid_page.selected_paths()
        if not paths:
            return
        dlg = BatchDialog(paths, self)
        dlg.finished.connect(self._after_batch)
        dlg.exec()

    def _grid_context(self, pos, paths: List[str]) -> None:
        menu = self._build_context_menu(paths if paths else None)
        menu.exec(pos)
        menu.deleteLater()

    def contextMenuEvent(self, event) -> None:
        if self.stack.currentWidget() is self.grid_page:
            paths = self.grid_page.selected_paths()
            menu = self._build_context_menu(paths if paths else None)
            menu.exec(event.globalPos())
            menu.deleteLater()
            return
        menu = self._build_context_menu(None)
        menu.exec(event.globalPos())
        menu.deleteLater()

    # ================================================================== 事件
    def _open_from_grid(self, path: str) -> None:
        self.stack.setCurrentWidget(self.canvas)
        self.actions["view.grid"].setChecked(False)
        self.open_path(path)
        self.canvas.setFocus()

    def _on_tree_click(self, index: QModelIndex) -> None:
        path = self.fs_model.filePath(index)
        if os.path.isdir(path):
            self.open_folder(path, switch_grid=False)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            if self.slide_timer.isActive():
                self.toggle_slideshow()
                return
            if self.isFullScreen():
                self.toggle_fullscreen()
                return
        if key == Qt.Key.Key_Space:
            if self.canvas.mode == MODE_VIEW and self.stack.currentWidget() is self.canvas:
                self.step(1)
                return
        if key == Qt.Key.Key_F11:
            self.toggle_fullscreen()
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if not urls:
            return
        path = urls[0].toLocalFile()
        if os.path.isdir(path):
            self.open_folder(path, switch_grid=True)
        elif os.path.isfile(path):
            self.open_path(path)
        event.acceptProposedAction()

    def closeEvent(self, event) -> None:
        if self.dirty and not self._confirm_discard():
            event.ignore()
            return
        try:
            self.cfg.q.setValue("window/geometry", self.saveGeometry())
            self.cfg.q.sync()
        except Exception:
            pass
        self.anim_timer.stop()
        self.slide_timer.stop()
        self.pool.wait(1500)
        event.accept()
