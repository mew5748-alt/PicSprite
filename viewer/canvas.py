# -*- coding: utf-8 -*-
"""图片显示画布：缩放、平移、旋转翻转预览、裁剪、涂鸦、添加文字。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSizeF, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetrics, QImage, QPainter,
                           QPainterPath, QPen, QPixmap, QTransform)
from PySide6.QtWidgets import QWidget

MIN_ZOOM = 0.02
MAX_ZOOM = 32.0

MODE_VIEW = "view"
MODE_CROP = "crop"
MODE_DRAW = "draw"
MODE_TEXT = "text"


class ImageCanvas(QWidget):
    zoomChanged = Signal(float)          # 百分比
    editCommitted = Signal(QImage, QImage)   # (修改前, 修改后)
    cursorMoved = Signal(object)         # (x, y) 或 None
    toolChanged = Signal(str)
    doubleClicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(240, 180)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

        self._image: Optional[QImage] = None
        self._rot = 0
        self._fh = False
        self._fv = False
        self._zoom = 1.0
        self._offset = QPointF(0, 0)
        self._fit_mode = True

        self._mode = MODE_VIEW
        self._crop = QRectF()
        self._ratio: Optional[float] = None
        self._drag = ""
        self._handle = -1
        self._press_pos = QPointF()
        self._press_crop = QRectF()
        self._pan_anchor = QPointF()
        self._last_pt: Optional[QPointF] = None
        self._stroke_before: Optional[QImage] = None

        self.brush_color = QColor("#ff3b30")
        self.brush_width = 6

        self._text_item: Optional[dict] = None
        self._text_drag_from = QPointF()

        self._bg = QColor("#2f3136")
        self._checker = True
        self._checker_pm = self._make_checker()

    # ------------------------------------------------------------------ 基础
    def _make_checker(self) -> QPixmap:
        pm = QPixmap(24, 24)
        pm.fill(QColor("#ffffff"))
        p = QPainter(pm)
        c = QColor("#e2e5ea")
        p.fillRect(0, 0, 12, 12, c)
        p.fillRect(12, 12, 12, 12, c)
        p.end()
        return pm

    def set_background(self, color: str) -> None:
        self._bg = QColor(color)
        self.update()

    def set_checkerboard(self, on: bool) -> None:
        self._checker = on
        self.update()

    def set_image(self, image: Optional[QImage], fit: bool = False) -> None:
        self._image = image
        self.cancel_tool()
        if fit or self._fit_mode:
            self.fit_to_window()
        else:
            self._clamp_offset()
            self.update()
        self._emit_zoom()

    def image(self) -> Optional[QImage]:
        return self._image

    def has_image(self) -> bool:
        return self._image is not None and not self._image.isNull()

    @property
    def mode(self) -> str:
        return self._mode

    # ------------------------------------------------------------------ 视图变换
    @property
    def rotation(self) -> int:
        return self._rot

    @property
    def flip_h(self) -> bool:
        return self._fh

    @property
    def flip_v(self) -> bool:
        return self._fv

    def has_view_transform(self) -> bool:
        return self._rot % 360 != 0 or self._fh or self._fv

    def clear_view_transform(self) -> None:
        self._rot = 0
        self._fh = False
        self._fv = False

    def rotate_by(self, delta: int) -> None:
        if not self.has_image():
            return
        if self._mode in (MODE_CROP, MODE_DRAW, MODE_TEXT):
            self.cancel_tool()
        self._rot = (self._rot + delta) % 360
        if self._fit_mode:
            self.fit_to_window()
        else:
            self._center()
        self.update()

    def flip(self, horizontal: bool) -> None:
        if not self.has_image():
            return
        if self._mode in (MODE_CROP, MODE_DRAW, MODE_TEXT):
            self.cancel_tool()
        if horizontal:
            self._fh = not self._fh
        else:
            self._fv = not self._fv
        self.update()

    def bake_transform(self) -> bool:
        """把临时旋转/翻转应用到像素，返回是否有变化。"""
        if not self.has_image() or not self.has_view_transform():
            return False
        from .imageio import apply_transform
        before = self._image
        after = apply_transform(before, self._rot, self._fh, self._fv)
        self._rot, self._fh, self._fv = 0, False, False
        self._image = after
        self.editCommitted.emit(before, after)
        self.fit_to_window()
        return True

    # ------------------------------------------------------------------ 尺寸/缩放
    def display_size(self) -> tuple:
        if not self.has_image():
            return (0, 0)
        w, h = self._image.width(), self._image.height()
        if self._rot % 180 == 90:
            w, h = h, w
        return (w, h)

    def _image_rect(self) -> QRectF:
        w, h = self.display_size()
        return QRectF(self._offset.x(), self._offset.y(), w * self._zoom, h * self._zoom)

    def zoom(self) -> float:
        return self._zoom

    def fit_to_window(self) -> None:
        if not self.has_image():
            return
        w, h = self.display_size()
        if w <= 0 or h <= 0:
            return
        s = min((self.width() - 16) / w, (self.height() - 16) / h)
        s = max(MIN_ZOOM, min(s, 4.0))
        self._zoom = s
        self._fit_mode = True
        self._center()
        self.update()
        self._emit_zoom()

    def actual_size(self) -> None:
        if not self.has_image():
            return
        self._fit_mode = False
        self._zoom = 1.0
        self._center()
        self.update()
        self._emit_zoom()

    def _center(self) -> None:
        w, h = self.display_size()
        self._offset = QPointF((self.width() - w * self._zoom) / 2,
                               (self.height() - h * self._zoom) / 2)

    def zoom_in(self) -> None:
        self.zoom_at(1.25, QPointF(self.width() / 2, self.height() / 2))

    def zoom_out(self) -> None:
        self.zoom_at(1 / 1.25, QPointF(self.width() / 2, self.height() / 2))

    def zoom_at(self, factor: float, anchor: QPointF) -> None:
        if not self.has_image():
            return
        old = self._zoom
        new = max(MIN_ZOOM, min(MAX_ZOOM, old * factor))
        if abs(new - old) < 1e-9:
            return
        img_pt = self._to_image(anchor)
        self._zoom = new
        self._offset = QPointF(anchor.x() - img_pt.x() * new, anchor.y() - img_pt.y() * new)
        self._fit_mode = False
        self._clamp_offset()
        self.update()
        self._emit_zoom()

    def set_zoom(self, percent: float, anchor: Optional[QPointF] = None) -> None:
        if not self.has_image():
            return
        target = max(MIN_ZOOM, min(MAX_ZOOM, percent / 100.0))
        anchor = anchor or QPointF(self.width() / 2, self.height() / 2)
        self.zoom_at(target / max(self._zoom, 1e-9), anchor)

    def _emit_zoom(self) -> None:
        self.zoomChanged.emit(self._zoom * 100.0)

    def _clamp_offset(self) -> None:
        w, h = self.display_size()
        dw, dh = w * self._zoom, h * self._zoom
        pad = 56.0
        if dw <= self.width():
            ox = (self.width() - dw) / 2
        else:
            ox = min(pad, max(self.width() - dw - pad, self._offset.x()))
        if dh <= self.height():
            oy = (self.height() - dh) / 2
        else:
            oy = min(pad, max(self.height() - dh - pad, self._offset.y()))
        self._offset = QPointF(ox, oy)

    # ------------------------------------------------------------------ 坐标换算
    def _to_image(self, pt: QPointF) -> QPointF:
        if self._zoom <= 0:
            return QPointF(0, 0)
        return (pt - self._offset) / self._zoom

    def _to_widget(self, pt: QPointF) -> QPointF:
        return pt * self._zoom + self._offset

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), self._bg)
        if not self.has_image():
            p.setPen(QColor("#9aa0a8"))
            f = p.font()
            f.setPointSize(12)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "拖入图片，或按 Ctrl+O 打开\n支持 BMP / JPG / PNG / GIF / TIFF / ICO / WebP")
            p.end()
            return

        target = self._image_rect()
        has_alpha = self._image.hasAlphaChannel()
        if has_alpha and self._checker:
            p.drawTiledPixmap(target, self._checker_pm)

        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.save()
        p.translate(target.center())
        if self._rot:
            p.rotate(self._rot)
        if self._fh or self._fv:
            p.scale(-1 if self._fh else 1, -1 if self._fv else 1)
        src = QRectF(0, 0, self._image.width(), self._image.height())
        p.drawImage(QRectF(-target.width() / 2, -target.height() / 2,
                           target.width(), target.height()), self._image, src)
        p.restore()

        # 细边框，深色背景上更清晰
        pen = QPen(QColor(255, 255, 255, 40), 1)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(target.adjusted(-0.5, -0.5, 0.5, 0.5))

        if self._mode == MODE_CROP:
            self._paint_crop(p)
        if self._mode == MODE_TEXT and self._text_item is not None:
            self._paint_text_preview(p)
        p.end()

    def _paint_crop(self, p: QPainter) -> None:
        r = self._crop_widget_rect()
        shade = QColor(0, 0, 0, 120)
        ir = self._image_rect()
        p.fillRect(QRectF(ir.left(), ir.top(), ir.width(), max(0, r.top() - ir.top())), shade)
        p.fillRect(QRectF(ir.left(), r.bottom(), ir.width(), max(0, ir.bottom() - r.bottom())), shade)
        p.fillRect(QRectF(ir.left(), r.top(), max(0, r.left() - ir.left()), r.height()), shade)
        p.fillRect(QRectF(r.right(), r.top(), max(0, ir.right() - r.right()), r.height()), shade)

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 230), 1.4))
        p.drawRect(r)
        # 三分线
        p.setPen(QPen(QColor(255, 255, 255, 90), 1, Qt.PenStyle.DashLine))
        for i in (1, 2):
            x = r.left() + r.width() * i / 3
            y = r.top() + r.height() * i / 3
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))

        p.setPen(QPen(QColor(40, 44, 52), 1.2))
        p.setBrush(QBrush(QColor("#ffffff")))
        for hr in self._handle_rects(r):
            p.drawRoundedRect(hr, 1.5, 1.5)

        # 尺寸提示
        w = int(self._crop.width())
        h = int(self._crop.height())
        label = f"{w} × {h}"
        p.setFont(self.font())
        fm = QFontMetrics(p.font())
        tw = fm.horizontalAdvance(label) + 14
        th = fm.height() + 6
        box = QRectF(r.left(), max(0, r.top() - th - 6), tw, th)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 165))
        p.drawRoundedRect(box, 4, 4)
        p.setPen(QColor("#ffffff"))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, label)

    def _paint_text_preview(self, p: QPainter) -> None:
        p.save()
        p.translate(self._offset)
        p.scale(self._zoom, self._zoom)
        self._render_text(p, self._text_item)
        p.restore()
        # 虚线包围框
        rect = self._text_bounds_widget()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(47, 111, 237, 220), 1, Qt.PenStyle.DashLine))
        p.drawRect(rect)

    def _text_block(self, painter: QPainter, item: dict):
        painter.setFont(item["font"])
        fm = QFontMetrics(item["font"])
        lines = item["text"].split("\n") or [""]
        width = max(fm.horizontalAdvance(l) for l in lines)
        height = fm.height() * len(lines)
        return fm, lines, width, height

    def _render_text(self, p: QPainter, item: dict) -> None:
        fm, lines, width, height = self._text_block(p, item)
        pos = item["pos"]
        left = pos.x() - width / 2
        top = pos.y() - height / 2
        for i, line in enumerate(lines):
            if not line:
                continue
            baseline = top + i * fm.height() + fm.ascent()
            lw = fm.horizontalAdvance(line)
            x = left + (width - lw) / 2
            if item.get("outline"):
                path = QPainterPath()
                path.addText(QPointF(x, baseline), item["font"], line)
                ow = max(1.5, item["font"].pointSizeF() * 0.16)
                p.setPen(QPen(item.get("outline_color", QColor("#000000")), ow,
                              Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                              Qt.PenJoinStyle.RoundJoin))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPath(path)
                p.fillPath(path, item["color"])
            else:
                p.setPen(item["color"])
                p.drawText(QPointF(x, baseline), line)

    def _text_bounds_widget(self) -> QRectF:
        item = self._text_item
        if item is None:
            return QRectF()
        tmp = QPainter(self._checker_pm)
        fm, lines, width, height = self._text_block(tmp, item)
        tmp.end()
        tl = QPointF(item["pos"].x() - width / 2, item["pos"].y() - height / 2)
        br = QPointF(item["pos"].x() + width / 2, item["pos"].y() + height / 2)
        return QRectF(self._to_widget(tl), self._to_widget(br)).adjusted(-4, -4, 4, 4)

    # ------------------------------------------------------------------ 裁剪
    def _crop_widget_rect(self) -> QRectF:
        tl = self._to_widget(self._crop.topLeft())
        return QRectF(tl, QSizeF(self._crop.width() * self._zoom,
                                 self._crop.height() * self._zoom))

    def _handle_rects(self, r: QRectF) -> list:
        s = 5.0
        pts = [
            (r.left(), r.top()), (r.center().x(), r.top()), (r.right(), r.top()),
            (r.right(), r.center().y()), (r.right(), r.bottom()),
            (r.center().x(), r.bottom()), (r.left(), r.bottom()), (r.left(), r.center().y()),
        ]
        return [QRectF(x - s, y - s, s * 2, s * 2) for x, y in pts]

    def begin_crop(self, ratio: Optional[float] = None) -> None:
        if not self.has_image():
            return
        if self._mode != MODE_CROP:
            self.bake_transform()
        self._mode = MODE_CROP
        self._ratio = ratio
        w, h = self._image.width(), self._image.height()
        # 初始选区为画面 80%
        cw, ch = w * 0.8, h * 0.8
        if ratio:
            if cw / ch > ratio:
                cw = ch * ratio
            else:
                ch = cw / ratio
        self._crop = QRectF((w - cw) / 2, (h - ch) / 2, cw, ch)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.toolChanged.emit(MODE_CROP)
        self.update()

    def set_crop_ratio(self, ratio: Optional[float]) -> None:
        self._ratio = ratio
        if self._mode == MODE_CROP and ratio and self._crop.height() > 0:
            w = self._crop.width()
            h = w / ratio
            if self._crop.y() + h > self._image.height():
                h = self._image.height() - self._crop.y()
                w = h * ratio
            self._crop.setWidth(w)
            self._crop.setHeight(h)
            self.update()

    def apply_crop(self) -> bool:
        if self._mode != MODE_CROP or not self.has_image():
            return False
        r = self._crop.intersected(QRectF(0, 0, self._image.width(), self._image.height()))
        rect = QRect(int(round(r.x())), int(round(r.y())),
                     int(round(r.width())), int(round(r.height())))
        if rect.width() < 2 or rect.height() < 2:
            return False
        before = self._image
        after = before.copy(rect)
        self._mode = MODE_VIEW
        self._crop = QRectF()
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._image = after
        self.editCommitted.emit(before, after)
        self.fit_to_window()
        self.toolChanged.emit(MODE_VIEW)
        return True

    def cancel_tool(self) -> None:
        was = self._mode
        self._mode = MODE_VIEW
        self._crop = QRectF()
        self._text_item = None
        self._last_pt = None
        self._drag = ""
        self.unsetCursor()
        if was != MODE_VIEW:
            self.toolChanged.emit(MODE_VIEW)
        self.update()

    # ------------------------------------------------------------------ 涂鸦
    def begin_draw(self) -> None:
        if not self.has_image():
            return
        self.bake_transform()
        self._mode = MODE_DRAW
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.toolChanged.emit(MODE_DRAW)
        self.update()

    def begin_text(self, text: str, font: QFont, color: QColor, outline: bool) -> None:
        if not self.has_image():
            return
        self.bake_transform()
        self._mode = MODE_TEXT
        self._text_item = {
            "text": text, "font": font, "color": color, "outline": outline,
            "outline_color": QColor("#000000"),
            "pos": QPointF(self._image.width() / 2, self._image.height() / 2),
        }
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.toolChanged.emit(MODE_TEXT)
        self.update()

    def commit_text(self) -> bool:
        if self._mode != MODE_TEXT or self._text_item is None or not self.has_image():
            return False
        before = self._image
        after = before.copy()
        p = QPainter(after)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        self._render_text(p, self._text_item)
        p.end()
        self._text_item = None
        self._mode = MODE_VIEW
        self.unsetCursor()
        self._image = after
        self.editCommitted.emit(before, after)
        self.toolChanged.emit(MODE_VIEW)
        self.update()
        return True

    # ------------------------------------------------------------------ 事件
    def resizeEvent(self, event) -> None:
        if self._fit_mode:
            self.fit_to_window()
        else:
            self._clamp_offset()
        super().resizeEvent(event)

    def wheelEvent(self, event) -> None:
        if not self.has_image():
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.0015 ** delta
        self.zoom_at(factor, QPointF(event.position()))
        event.accept()

    def _crop_hit(self, pt: QPointF) -> int:
        r = self._crop_widget_rect()
        for i, hr in enumerate(self._handle_rects(r)):
            if hr.contains(pt):
                return i
        if r.contains(pt):
            return 8
        return -1

    def mousePressEvent(self, event) -> None:
        if not self.has_image():
            return
        pt = QPointF(event.position())
        if event.button() == Qt.MouseButton.MiddleButton:
            self._drag = "pan"
            self._pan_anchor = pt - self._offset
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        if self._mode == MODE_CROP:
            h = self._crop_hit(pt)
            if h >= 0:
                self._drag = "crop_move" if h == 8 else "crop_resize"
                self._handle = h
                self._press_pos = pt
                self._press_crop = QRectF(self._crop)
            else:
                # 空白处按下 → 重新拉一个选区
                self._drag = "crop_new"
                self._press_pos = pt
                self._crop = QRectF(self._to_image(pt), QSizeF(0, 0))
            return

        if self._mode == MODE_DRAW:
            self._drag = "draw"
            self._stroke_before = self._image.copy()
            self._image = self._image.copy()
            self._last_pt = self._to_image(pt)
            self._paint_stroke(self._last_pt, self._last_pt)
            return

        if self._mode == MODE_TEXT:
            if self._text_item is not None and not self._text_bounds_widget().contains(pt):
                self._text_item["pos"] = self._to_image(pt)
                self.update()
            self._text_drag_from = pt
            self._drag = "text_move"
            return

        self._drag = "pan"
        self._pan_anchor = pt - self._offset
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def _paint_stroke(self, p1: QPointF, p2: QPointF) -> None:
        if self._image is None:
            return
        p = QPainter(self._image)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(self.brush_color, self.brush_width, Qt.PenStyle.SolidLine,
                   Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        if p1 == p2:
            p.drawPoint(p1)
        else:
            p.drawLine(p1, p2)
        p.end()
        self.update()

    def mouseMoveEvent(self, event) -> None:
        pt = QPointF(event.position())
        if self.has_image():
            ip = self._to_image(pt)
            if 0 <= ip.x() < self._image.width() and 0 <= ip.y() < self._image.height():
                self.cursorMoved.emit((int(ip.x()), int(ip.y())))
            else:
                self.cursorMoved.emit(None)

        if self._drag == "pan":
            self._offset = pt - self._pan_anchor
            self._clamp_offset()
            self.update()
            return

        if self._drag == "draw" and self._mode == MODE_DRAW:
            cur = self._to_image(pt)
            self._paint_stroke(self._last_pt or cur, cur)
            self._last_pt = cur
            return

        if self._drag in ("crop_move", "crop_resize", "crop_new"):
            self._drag_crop(pt)
            return

        if self._drag == "text_move" and self._text_item is not None:
            delta = (pt - self._text_drag_from) / self._zoom
            self._text_item["pos"] += delta
            self._text_drag_from = pt
            self.update()
            return

        # 悬停光标
        if self._mode == MODE_CROP:
            h = self._crop_hit(pt)
            cursors = [Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeVerCursor,
                       Qt.CursorShape.SizeBDiagCursor, Qt.CursorShape.SizeHorCursor,
                       Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeVerCursor,
                       Qt.CursorShape.SizeBDiagCursor, Qt.CursorShape.SizeHorCursor]
            if h == 8:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            elif h >= 0:
                self.setCursor(cursors[h])
            else:
                self.setCursor(Qt.CursorShape.CrossCursor)
        elif self._mode == MODE_VIEW:
            self.setCursor(Qt.CursorShape.OpenHandCursor if self._zoom > 1.0
                           else Qt.CursorShape.ArrowCursor)

    def _drag_crop(self, pt: QPointF) -> None:
        img_pt = self._to_image(pt)
        press_img = self._to_image(self._press_pos)
        c = QRectF(self._press_crop)
        if self._drag == "crop_new":
            r = QRectF(press_img, img_pt).normalized()
            if self._ratio and r.width() > 2:
                h = r.width() / self._ratio
                if img_pt.y() < press_img.y():
                    r.setTop(r.bottom() - h)
                else:
                    r.setBottom(r.top() + h)
            lim = QRectF(0, 0, self._image.width(), self._image.height())
            r = r.intersected(lim)
            if r.width() >= 4 and r.height() >= 4:
                self._crop = r
                self.update()
            return
        if self._drag == "crop_move":
            moved = img_pt - press_img
            c.translate(moved)
            w, h = self._image.width(), self._image.height()
            if c.left() < 0:
                c.moveLeft(0)
            if c.top() < 0:
                c.moveTop(0)
            if c.right() > w:
                c.moveRight(w)
            if c.bottom() > h:
                c.moveBottom(h)
        else:
            idx = self._handle
            left, top, right, bottom = c.left(), c.top(), c.right(), c.bottom()
            if idx in (0, 6, 7):
                left = min(img_pt.x(), right - 4)
            if idx in (2, 3, 4):
                right = max(img_pt.x(), left + 4)
            if idx in (0, 1, 2):
                top = min(img_pt.y(), bottom - 4)
            if idx in (4, 5, 6):
                bottom = max(img_pt.y(), top + 4)
            c = QRectF(QPointF(left, top), QPointF(right, bottom))
            if self._ratio:
                if idx in (1, 5):
                    h = c.width() / self._ratio
                    if idx == 1:
                        c.setTop(c.bottom() - h)
                    else:
                        c.setBottom(c.top() + h)
                elif idx in (3, 7):
                    w = c.height() * self._ratio
                    if idx == 7:
                        c.setLeft(c.right() - w)
                    else:
                        c.setRight(c.left() + w)
                else:
                    h = c.width() / self._ratio
                    if idx in (0, 2):
                        c.setTop(c.bottom() - h) if idx == 0 else c.setBottom(c.top() + h)
                    else:
                        w = c.height() * self._ratio
                        c.setWidth(w)
        w, h = self._image.width(), self._image.height()
        c = c.intersected(QRectF(0, 0, w, h))
        if c.width() >= 4 and c.height() >= 4:
            self._crop = c
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._drag == "pan":
            if self._mode == MODE_VIEW:
                self.setCursor(Qt.CursorShape.OpenHandCursor if self._zoom > 1.0
                               else Qt.CursorShape.ArrowCursor)
        elif self._drag == "draw" and self._mode == MODE_DRAW:
            if self._stroke_before is not None:
                before, after = self._stroke_before, self._image
                self._stroke_before = None
                if before is not after:
                    self.editCommitted.emit(before, after)
        self._drag = ""
        self._handle = -1

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._mode == MODE_VIEW:
            self.doubleClicked.emit()
        else:
            super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key == Qt.Key.Key_Escape:
            if self._mode != MODE_VIEW:
                self.cancel_tool()
                return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._mode == MODE_CROP:
                self.apply_crop()
                return
            if self._mode == MODE_TEXT:
                self.commit_text()
                return
        if key == Qt.Key.Key_Space and self._mode == MODE_CROP:
            self._crop = QRectF(0, 0, self._image.width(), self._image.height())
            self.update()
            return
        super().keyPressEvent(event)
