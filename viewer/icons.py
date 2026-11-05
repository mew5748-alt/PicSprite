# -*- coding: utf-8 -*-
"""用 QPainter 现场绘制线性图标，避免依赖外部资源。"""
from __future__ import annotations

import math
from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap,
                           QPolygonF)

ICON_COLOR = "#3d434c"

_cache = {}


def _stroke(p: QPainter, pts, close: bool = False) -> None:
    if not pts:
        return
    path = QPainterPath(QPointF(*pts[0]))
    for pt in pts[1:]:
        path.lineTo(QPointF(*pt))
    if close:
        path.closeSubpath()
    p.drawPath(path)


def _arrow_head(p: QPainter, tip, angle: float, size: float = 4.2) -> None:
    for da in (150, -150):
        b = math.radians(angle + da)
        p.drawLine(QPointF(*tip),
                   QPointF(tip[0] + size * math.cos(b), tip[1] + size * math.sin(b)))


def _draw(p: QPainter, name: str) -> None:
    if name == "open" or name == "folder":
        _stroke(p, [(3, 7), (9.5, 7), (11.5, 9.5), (21, 9.5), (21, 19.5), (3, 19.5)], True)
        if name == "open":
            _stroke(p, [(3, 19.5), (6, 12.5), (22.5, 12.5), (19.5, 19.5)])
    elif name == "reload":
        p.drawArc(QRectF(4, 4, 16, 16), 40 * 16, 270 * 16)
        _arrow_head(p, (16.6, 3.4), 10)
    elif name == "save":
        _stroke(p, [(4, 4), (17, 4), (20, 7), (20, 20), (4, 20)], True)
        _stroke(p, [(8, 4), (8, 9.5), (15, 9.5), (15, 4)])
        _stroke(p, [(7.5, 20), (7.5, 13.5), (16.5, 13.5), (16.5, 20)])
    elif name == "saveas":
        _stroke(p, [(4, 4), (16, 4), (19, 7), (19, 15), (4, 15)], True)
        _stroke(p, [(8, 4), (8, 9), (14, 9), (14, 4)])
        _stroke(p, [(3, 19), (10, 19)])
        _arrow_head(p, (13.5, 19), 0)
    elif name == "compress":
        _stroke(p, [(8.5, 3.5), (3.5, 3.5), (3.5, 8.5)])
        _stroke(p, [(15.5, 20.5), (20.5, 20.5), (20.5, 15.5)])
        _stroke(p, [(4.6, 4.6), (9.4, 9.4)])
        _arrow_head(p, (9.4, 9.4), 45)
        _stroke(p, [(19.4, 19.4), (14.6, 14.6)])
        _arrow_head(p, (14.6, 14.6), 225)
    elif name == "print":
        p.drawRect(QRectF(3.5, 8.5, 17, 8.5))               # 机身
        _stroke(p, [(7, 8.5), (7, 3.5), (17, 3.5), (17, 8.5)], True)      # 进纸
        _stroke(p, [(7, 13.5), (7, 20.5), (17, 20.5), (17, 13.5)], True)  # 出纸
        _stroke(p, [(9.5, 16.2), (14.5, 16.2)])
        _stroke(p, [(9.5, 18.3), (14.5, 18.3)])
        p.drawPoint(QPointF(17.8, 11.2))
    elif name == "rename":
        _stroke(p, [(4, 20), (5.4, 15.4), (16.4, 4.4), (19.6, 7.6), (8.6, 18.6)], True)
        _stroke(p, [(14, 20), (21, 20)])
    elif name == "delete":
        _stroke(p, [(3.5, 6.5), (20.5, 6.5)])
        _stroke(p, [(9, 6.5), (9, 3.5), (15, 3.5), (15, 6.5)])
        _stroke(p, [(5.5, 6.5), (6.8, 20.5), (17.2, 20.5), (18.5, 6.5)])
        _stroke(p, [(10, 10), (10.6, 17)])
        _stroke(p, [(14, 10), (13.4, 17)])
    elif name == "copy":
        _stroke(p, [(3.5, 3.5), (14, 3.5), (14, 14), (3.5, 14)], True)
        _stroke(p, [(7.5, 17), (7.5, 20.5), (20.5, 20.5), (20.5, 7.5), (17, 7.5)])
    elif name == "paste":
        _stroke(p, [(5, 5), (9, 5), (9, 3), (15, 3), (15, 5), (19, 5), (19, 21), (5, 21)], True)
        _stroke(p, [(9, 11), (15, 11)])
        _stroke(p, [(9, 15), (15, 15)])
    elif name == "path":
        _stroke(p, [(4, 7), (4, 20), (20, 20), (20, 7)])
        _stroke(p, [(2, 7), (22, 7)])
        _stroke(p, [(12, 3), (12, 20)])
    elif name == "info":
        p.drawEllipse(QRectF(3.5, 3.5, 17, 17))
        _stroke(p, [(12, 10.5), (12, 16.5)])
        p.drawPoint(QPointF(12, 7.6))
    elif name == "close":
        _stroke(p, [(6, 6), (18, 18)])
        _stroke(p, [(18, 6), (6, 18)])
    elif name == "undo":
        p.drawArc(QRectF(4.5, 5.5, 15, 14), 30 * 16, 200 * 16)
        _arrow_head(p, (4.2, 12.4), 180)
    elif name == "redo":
        p.drawArc(QRectF(4.5, 5.5, 15, 14), -50 * 16, 200 * 16)
        _arrow_head(p, (19.8, 12.4), 0)
    elif name == "crop":
        _stroke(p, [(7, 2.5), (7, 17), (21.5, 17)])
        _stroke(p, [(2.5, 7), (17, 7), (17, 21.5)])
    elif name == "pen":
        _stroke(p, [(4, 20), (5.6, 14.8), (15.8, 4.6), (19.4, 8.2), (9.2, 18.4)], True)
        _stroke(p, [(13.6, 6.8), (17.2, 10.4)])
    elif name == "text":
        _stroke(p, [(5, 5.5), (19, 5.5)])
        _stroke(p, [(12, 5.5), (12, 19.5)])
        _stroke(p, [(8.6, 19.5), (15.4, 19.5)])
    elif name == "resize":
        _stroke(p, [(4, 4), (20, 4), (20, 20), (4, 20)], True)
        _stroke(p, [(9, 9), (9, 15), (15, 15), (15, 9)], True)
        _arrow_head(p, (18.6, 18.6), 45)
    elif name == "grid":
        _stroke(p, [(4, 4), (10.5, 4), (10.5, 10.5), (4, 10.5)], True)
        _stroke(p, [(13.5, 4), (20, 4), (20, 10.5), (13.5, 10.5)], True)
        _stroke(p, [(4, 13.5), (10.5, 13.5), (10.5, 20), (4, 20)], True)
        _stroke(p, [(13.5, 13.5), (20, 13.5), (20, 20), (13.5, 20)], True)
    elif name == "fullscreen":
        _stroke(p, [(4, 9), (4, 4), (9, 4)])
        _stroke(p, [(15, 4), (20, 4), (20, 9)])
        _stroke(p, [(20, 15), (20, 20), (15, 20)])
        _stroke(p, [(9, 20), (4, 20), (4, 15)])
    elif name == "fit":
        _stroke(p, [(9, 5), (5, 5), (5, 9)])
        _stroke(p, [(15, 5), (19, 5), (19, 9)])
        _stroke(p, [(19, 15), (19, 19), (15, 19)])
        _stroke(p, [(9, 19), (5, 19), (5, 15)])
        p.drawRect(QRectF(9, 8, 6, 8))
    elif name == "actual":
        p.drawRect(QRectF(4.5, 6, 15, 12))
        _stroke(p, [(8, 14.5), (8, 9.5), (6.5, 10.5)])
        _stroke(p, [(11.5, 14.5), (11.5, 9.5), (16, 14.5), (16, 9.5)])
    elif name == "slideshow":
        _stroke(p, [(8, 5), (19, 12), (8, 19)], True)
    elif name == "zoom_in" or name == "zoom_out":
        p.drawEllipse(QRectF(4, 4, 12.5, 12.5))
        _stroke(p, [(15.5, 15.5), (20.5, 20.5)])
        _stroke(p, [(7, 10.2), (13.5, 10.2)])
        if name == "zoom_in":
            _stroke(p, [(10.25, 7), (10.25, 13.5)])
    elif name == "prev":
        _stroke(p, [(14.5, 5), (8, 12), (14.5, 19)])
    elif name == "next":
        _stroke(p, [(9.5, 5), (16, 12), (9.5, 19)])
    elif name in ("rotate_l", "rotate_r"):
        if name == "rotate_l":
            p.drawArc(QRectF(4, 4.5, 16, 15), 110 * 16, 250 * 16)
            _arrow_head(p, (4.6, 11.2), 160)
        else:
            p.drawArc(QRectF(4, 4.5, 16, 15), -180 * 16, 250 * 16)
            _arrow_head(p, (19.4, 11.2), 20)
    elif name in ("flip_h", "flip_v"):
        p.save()
        if name == "flip_v":
            p.translate(12, 12)
            p.rotate(90)
            p.translate(-12, -12)
        pen = p.pen()
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        _stroke(p, [(12, 2.8), (12, 21.2)])
        pen.setStyle(Qt.PenStyle.SolidLine)
        p.setPen(pen)
        _stroke(p, [(9.4, 5), (4, 12), (9.4, 19)], True)
        _stroke(p, [(14.6, 5), (20, 12), (14.6, 19)], True)
        p.restore()
    elif name == "batch":
        _stroke(p, [(7, 3), (21, 3), (21, 17)], False)
        _stroke(p, [(3, 7), (17, 7), (17, 21), (3, 21)], True)
        _stroke(p, [(7, 11), (13, 11)])
        _stroke(p, [(7, 15), (13, 15)])
    elif name == "settings":
        p.drawEllipse(QRectF(8.5, 8.5, 7, 7))
        for i in range(8):
            a = math.radians(i * 45)
            _stroke(p, [(12 + 8 * math.cos(a), 12 + 8 * math.sin(a)),
                        (12 + 10.5 * math.cos(a), 12 + 10.5 * math.sin(a))])
        p.drawEllipse(QRectF(4.6, 4.6, 14.8, 14.8))
    elif name == "wallpaper":
        _stroke(p, [(3, 4.5), (21, 4.5), (21, 16), (3, 16)], True)
        _stroke(p, [(9, 20), (15, 20)])
        _stroke(p, [(12, 16), (12, 20)])
        _stroke(p, [(3, 12), (8, 7.5), (12, 11), (16, 8), (21, 12)])
    elif name == "reveal":
        _stroke(p, [(3.5, 7), (9.5, 7), (11.5, 9.5), (20.5, 9.5), (20.5, 19.5), (3.5, 19.5)], True)
        _stroke(p, [(9, 14.5), (15.5, 14.5)])
        _arrow_head(p, (15.5, 14.5), 0)
    elif name == "keyboard":
        _stroke(p, [(2.5, 6.5), (21.5, 6.5), (21.5, 17.5), (2.5, 17.5)], True)
        for x in (6, 9.5, 13, 16.5):
            p.drawPoint(QPointF(x, 10.5))
        _stroke(p, [(7.5, 14), (16.5, 14)])
    elif name == "bg":
        p.drawEllipse(QRectF(4, 4, 16, 16))
        path = QPainterPath()
        path.moveTo(12, 4)
        path.arcTo(QRectF(4, 4, 16, 16), 90, -180)
        path.closeSubpath()
        p.fillPath(path, p.pen().color())
    elif name == "cache":
        p.drawEllipse(QRectF(4.5, 4, 15, 5))
        _stroke(p, [(4.5, 6.5), (4.5, 18), (19.5, 18), (19.5, 6.5)])
        p.drawArc(QRectF(4.5, 15.5, 15, 5), 180 * 16, 180 * 16)
    elif name == "image":
        _stroke(p, [(3.5, 4.5), (20.5, 4.5), (20.5, 19.5), (3.5, 19.5)], True)
        p.drawEllipse(QRectF(7, 8, 3.2, 3.2))
        _stroke(p, [(4.5, 18), (10, 12.5), (14, 16.5), (16.5, 14), (20, 17.5)])
    else:
        p.drawRect(QRectF(5, 5, 14, 14))


def pixmap(name: str, color: str = ICON_COLOR, size: int = 20, dpr: float = 2.0) -> QPixmap:
    key = (name, color, size, dpr)
    hit = _cache.get(key)
    if hit is not None:
        return hit
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.scale(size / 24.0, size / 24.0)
    pen = QPen(QColor(color), 1.85, Qt.PenStyle.SolidLine,
               Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    try:
        _draw(p, name)
    finally:
        p.end()
    _cache[key] = pm
    return pm


def icon(name: str, color: str = ICON_COLOR, size: int = 20) -> QIcon:
    key = ("icon", name, color, size)
    hit = _cache.get(key)
    if hit is not None:
        return hit
    ic = QIcon(pixmap(name, color, size))
    _cache[key] = ic
    return ic


def app_icon() -> QIcon:
    """程序图标：蓝色圆角方块 + 白色山峰。"""
    key = ("__app__",)
    if key in _cache:
        return _cache[key]
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(s, s)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.scale(s / 24.0, s / 24.0)
        path = QPainterPath()
        path.addRoundedRect(QRectF(1.5, 1.5, 21, 21), 5, 5)
        p.fillPath(path, QColor("#2f6fed"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(15.2, 5.6, 3.6, 3.6))
        mount = QPainterPath()
        mount.moveTo(4.2, 18.4)
        mount.lineTo(9.2, 10.6)
        mount.lineTo(12.6, 15.0)
        mount.lineTo(15.2, 11.8)
        mount.lineTo(20.0, 18.4)
        mount.closeSubpath()
        p.fillPath(mount, QColor("#ffffff"))
        p.end()
        ic.addPixmap(pm)
    _cache[key] = ic
    return ic
