# -*- coding: utf-8 -*-
"""界面样式（浅色主题，贴近 Windows 11 观感）。"""
from __future__ import annotations

import os

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap

FONT_FAMILY = '"Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif'

_QSS_TEMPLATE = f"""
QWidget {{
    font-family: {FONT_FAMILY};
    font-size: 13px;
    color: #22262b;
}}
QMainWindow, QDialog {{ background: #f5f6f8; }}
QDialog {{ background: #f7f8fa; }}

QToolBar {{
    background: #ffffff;
    border: 0;
    border-bottom: 1px solid #e6e8ec;
    padding: 4px 8px;
    spacing: 1px;
}}
QToolBar::separator {{
    background: #e6e8ec;
    width: 1px;
    margin: 6px 6px;
}}
QToolButton {{
    border: 0;
    border-radius: 6px;
    padding: 5px 7px;
    color: #2b3038;
    background: transparent;
}}
QToolButton:hover {{ background: #eef2fb; }}
QToolButton:pressed {{ background: #e0e8f8; }}
QToolButton:checked {{ background: #e3ecff; color: #1a56db; }}
QToolButton:disabled {{ color: #bcc2cc; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}

QMenuBar {{ background: #ffffff; border-bottom: 1px solid #e6e8ec; padding: 1px 4px; }}
QMenuBar::item {{ padding: 5px 10px; background: transparent; border-radius: 5px; }}
QMenuBar::item:selected {{ background: #eef2fb; }}
QMenu {{ background: #ffffff; border: 1px solid #e2e5ea; padding: 6px; }}
QMenu::item {{ padding: 6px 30px 6px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: #eef2fb; color: #1656d6; }}
QMenu::item:disabled {{ color: #b3b9c3; }}
QMenu::separator {{ height: 1px; background: #eceef2; margin: 5px 10px; }}
QMenu::icon {{ padding-left: 8px; }}

QStatusBar {{ background: #ffffff; border-top: 1px solid #e6e8ec; color: #5b6270; }}
QStatusBar::item {{ border: 0; }}
QStatusBar QLabel {{ color: #5b6270; padding: 0 6px; }}

QPushButton {{
    background: #ffffff;
    border: 1px solid #d7dbe2;
    border-radius: 7px;
    padding: 6px 16px;
    min-height: 16px;
}}
QPushButton:hover {{ border-color: #9fb4e0; background: #f8faff; }}
QPushButton:pressed {{ background: #eef2fb; }}
QPushButton:default {{ background: #2f6fed; color: #ffffff; border-color: #2f6fed; }}
QPushButton:default:hover {{ background: #1f5fdd; }}
QPushButton:disabled {{ color: #b0b6c0; background: #f2f3f6; border-color: #e4e6eb; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: #ffffff;
    border: 1px solid #d7dbe2;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 18px;
    selection-background-color: #cfe0ff;
    selection-color: #1b2a45;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border-color: #2f6fed; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ background: #f4f5f7; color: #a9afb9; }}
QComboBox::drop-down {{ border: 0; width: 22px; }}
QComboBox::down-arrow {{ image: url("__CHEV_DOWN__"); width: 10px; height: 10px; }}
QSpinBox, QDoubleSpinBox {{ padding-right: 20px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border; subcontrol-position: top right;
    width: 18px; margin: 2px 2px 0 0;
    border: 0; border-top-right-radius: 5px; background: transparent;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border; subcontrol-position: bottom right;
    width: 18px; margin: 0 2px 2px 0;
    border: 0; border-bottom-right-radius: 5px; background: transparent;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background: #e9effb; border-radius: 4px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url("__CHEV_UP__"); width: 8px; height: 8px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url("__CHEV_DOWN__"); width: 8px; height: 8px;
}}
QComboBox QAbstractItemView {{
    background: #ffffff;
    border: 1px solid #e2e5ea;
    padding: 4px;
    outline: 0;
    selection-background-color: #eef2fb;
    selection-color: #1656d6;
}}

QGroupBox {{
    border: 1px solid #e4e7ec;
    border-radius: 9px;
    margin-top: 14px;
    padding: 10px 10px 8px 10px;
    background: #ffffff;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    color: #4a5160;
    font-weight: 600;
}}

QTabWidget::pane {{
    border: 1px solid #e4e7ec;
    border-radius: 9px;
    background: #ffffff;
    top: -1px;
}}
QTabBar::tab {{
    padding: 7px 16px;
    margin-right: 3px;
    border-radius: 7px 7px 0 0;
    color: #5b6270;
    background: transparent;
}}
QTabBar::tab:hover {{ background: #eef2fb; }}
QTabBar::tab:selected {{ background: #ffffff; color: #1656d6; border: 1px solid #e4e7ec; border-bottom-color: #ffffff; }}

QTreeView, QListView, QTableWidget, QListWidget, QPlainTextEdit, QTextEdit {{
    background: #ffffff;
    border: 1px solid #e4e7ec;
    border-radius: 8px;
    outline: 0;
    alternate-background-color: #fafbfc;
}}
QTreeView::item {{ padding: 4px 2px; border-radius: 5px; }}
QTreeView::item:selected {{ background: #e3ecff; color: #1656d6; }}
QListWidget::item {{ border-radius: 8px; padding: 3px; }}
QListWidget::item:hover {{ background: #f3f6fd; }}
QListWidget::item:selected {{ background: #e3ecff; color: #1656d6; }}
QTreeView::item:hover {{ background: #f2f5fd; }}
QTableWidget::item:selected {{ background: #e3ecff; color: #1656d6; }}
QHeaderView::section {{
    background: #f4f6f9;
    border: 0;
    border-bottom: 1px solid #e4e7ec;
    padding: 6px 8px;
    color: #59606e;
    font-weight: 600;
}}
QTableWidget {{ gridline-color: #eef0f4; }}

/* 左侧缩略图栏：不要边框，和目录树连成一体 */
QWidget#stripPanel {{ background: transparent; }}
QListWidget#thumbStrip {{
    background: #ffffff;
    border: 1px solid #e4e7ec;
    border-radius: 8px;
    padding: 4px 2px;
}}
QListWidget#thumbStrip::item {{ border-radius: 7px; padding: 2px; margin: 1px; }}
QListWidget#thumbStrip::item:hover {{ background: #f3f6fd; }}
QListWidget#thumbStrip::item:selected {{ background: #e3ecff; color: #1656d6; }}
QListWidget#thumbStrip::item:selected:!active {{ background: #e3ecff; color: #1656d6; }}

QCheckBox, QRadioButton {{ spacing: 7px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 15px; height: 15px;
    border: 1px solid #c3c9d4;
    border-radius: 4px;
    background: #ffffff;
}}
QCheckBox::indicator:hover {{ border-color: #2f6fed; }}
QCheckBox::indicator:checked {{
    background: #2f6fed;
    border-color: #2f6fed;
    image: url("__CHECK__");
}}
QRadioButton::indicator {{ border-radius: 8px; }}
QRadioButton::indicator:checked {{ background: #2f6fed; border: 4px solid #ffffff; }}

QSlider::groove:horizontal {{ height: 4px; background: #e3e6ec; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: #9db8f2; border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 13px; height: 13px; margin: -6px 0;
    border-radius: 7px; background: #ffffff; border: 2px solid #2f6fed;
}}

QProgressBar {{
    border: 0; background: #eceff4; border-radius: 4px;
    height: 12px; text-align: center; color: #4a5160; font-size: 11px;
}}
QProgressBar::chunk {{ background: #2f6fed; border-radius: 4px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #c9cfd9; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #aab3c0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #c9cfd9; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QSplitter::handle {{ background: #e9ebef; }}
QSplitter::handle:horizontal {{ width: 3px; }}
QSplitter::handle:hover {{ background: #cfd6e2; }}

QDockWidget {{ color: #4a5160; }}
QDockWidget::title {{
    background: #f4f6f9;
    padding: 6px 10px;
    border-bottom: 1px solid #e4e7ec;
    text-align: left;
}}

QToolTip {{
    background: #2b3038; color: #ffffff; border: 0;
    padding: 4px 8px; border-radius: 4px;
}}
QLabel#hint {{ color: #8b919c; }}
QLabel#title {{ font-size: 15px; font-weight: 600; color: #1c2129; }}
QLabel#subtitle {{ color: #7b8290; }}
QFrame#card {{ background: #ffffff; border: 1px solid #e4e7ec; border-radius: 10px; }}
QLabel#stat {{ color: #1656d6; font-weight: 600; }}
QLabel#warn {{ color: #c0392b; }}
"""

def _make_png(name: str, size: int, draw) -> str:
    from .config import app_data_dir
    path = os.path.join(app_data_dir(), name)
    if not os.path.exists(path):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        draw(p, size)
        p.end()
        pm.save(path, "PNG")
    return path.replace("\\", "/")


def _check_icon_path() -> str:
    """白色对勾，用于复选框。"""

    def draw(p: QPainter, s: int) -> None:
        k = s / 36.0
        pen = QPen(QColor("#ffffff"), 4.6 * k, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawLine(QPointF(8 * k, 18 * k), QPointF(15 * k, 26 * k))
        p.drawLine(QPointF(15 * k, 26 * k), QPointF(28 * k, 9 * k))

    return _make_png("check.png", 36, draw)


def _chevron_path(up: bool) -> str:
    """下拉箭头。"""

    def draw(p: QPainter, s: int) -> None:
        k = s / 20.0
        pen = QPen(QColor("#6b7280"), 2.2 * k, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        if up:
            p.drawLine(QPointF(4 * k, 12.5 * k), QPointF(10 * k, 6.5 * k))
            p.drawLine(QPointF(10 * k, 6.5 * k), QPointF(16 * k, 12.5 * k))
        else:
            p.drawLine(QPointF(4 * k, 7.5 * k), QPointF(10 * k, 13.5 * k))
            p.drawLine(QPointF(10 * k, 13.5 * k), QPointF(16 * k, 7.5 * k))

    return _make_png("chevron_up.png" if up else "chevron_down.png", 20, draw)


def build_qss() -> str:
    qss = _QSS_TEMPLATE
    qss = qss.replace("__CHECK__", _check_icon_path())
    qss = qss.replace("__CHEV_DOWN__", _chevron_path(False))
    qss = qss.replace("__CHEV_UP__", _chevron_path(True))
    return qss


QSS = _QSS_TEMPLATE

DARK_CANVAS = "#2f3136"
MID_CANVAS = "#8a8d93"
LIGHT_CANVAS = "#eceef1"

CANVAS_COLORS = {"dark": DARK_CANVAS, "mid": MID_CANVAS, "light": LIGHT_CANVAS}
