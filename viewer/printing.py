# -*- coding: utf-8 -*-
"""打印与 PDF 导出：版面计算 + 绘制。

坐标模型（已用 PDF 输出实测确认）：把 QPainter 画到 QPrinter 上时，坐标原点就是
「纸张减去页边距」这一页可打印区域的左上角，viewport 尺寸等于
``printer.pageRect(DevicePixel)``。所以版面一律在 canvas 矩形内按 px_per_mm 计算，
打印、预览、导出 PDF 三处共用同一套绘制代码，所见即所得。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import QMarginsF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QImage, QPageLayout,
                           QPageSize, QPainter, QPen)
from PySide6.QtPrintSupport import QPrinter

FONT_FAMILY = "Microsoft YaHei UI"

# 缩放方式：(键, 界面文字)
SCALES: List[Tuple[str, str]] = [
    ("fit", "适应区域（完整显示）"),
    ("shrink", "原始大小（不放大）"),
    ("fill", "铺满区域（裁切）"),
]

PER_PAGES: List[int] = [1, 2, 4, 6, 9]

# 单双面：(键, 界面文字, QPrinter.DuplexMode)
DUPLEX_MODES: List[Tuple[str, str]] = [
    ("none", "单面打印"),
    ("long", "双面 · 长边翻转（书本式）"),
    ("short", "双面 · 短边翻转（便签式）"),
]

# 图片自身没写 DPI 时按 96 估算物理尺寸
FALLBACK_DPI = 96.0


@dataclass
class PrintItem:
    """一页里的一个图像单元。"""

    image: QImage
    title: str = ""
    date: str = ""


@dataclass
class PrintOptions:
    per_page: int = 1
    scale: str = "fit"
    margin_mm: float = 6.0
    gap_mm: float = 4.0
    show_title: bool = True
    show_date: bool = False
    duplex: str = "none"
    printer_name: str = ""

    @property
    def caption(self) -> bool:
        return self.show_title or self.show_date


# ---------------------------------------------------------------- 版面

def grid_for(per_page: int, landscape: bool) -> Tuple[int, int]:
    """返回 (列数, 行数)。按纸张方向给 2 张 / 6 张选更顺手的排法。"""
    per_page = max(1, int(per_page))
    if per_page == 2:
        return (2, 1) if landscape else (1, 2)
    if per_page == 4:
        return 2, 2
    if per_page == 6:
        return (3, 2) if landscape else (2, 3)
    if per_page == 9:
        return 3, 3
    side = max(1, int(math.ceil(math.sqrt(per_page))))
    return side, side


def page_count(total: int, per_page: int) -> int:
    if total <= 0:
        return 0
    return int(math.ceil(total / max(1, int(per_page))))


def paper_mm(printer: QPrinter) -> Tuple[float, float]:
    """纸张尺寸（已考虑方向），单位毫米。"""
    r = printer.pageLayout().fullRect(QPageLayout.Unit.Millimeter)
    return r.width(), r.height()


def canvas_rect(printer: QPrinter) -> QRectF:
    """可打印区域，单位设备像素（与 QPainter 的坐标系一致）。"""
    r = printer.pageRect(QPrinter.Unit.DevicePixel)
    return QRectF(0, 0, r.width(), r.height())


def apply_margins(printer: QPrinter, margin_mm: float) -> None:
    m = max(0.0, float(margin_mm))
    printer.setPageMargins(QMarginsF(m, m, m, m), QPageLayout.Unit.Millimeter)


_DUPLEX_MAP = {
    "none": QPrinter.DuplexMode.DuplexNone,
    "long": QPrinter.DuplexMode.DuplexLongSide,
    "short": QPrinter.DuplexMode.DuplexShortSide,
}


def apply_duplex(printer: QPrinter, key: str) -> None:
    """设置单/双面。打印机不支持时 Qt 会直接忽略，不会报错。"""
    mode = _DUPLEX_MAP.get(str(key or "none"))
    if mode is not None:
        try:
            printer.setDuplex(mode)
        except Exception:                                  # noqa: BLE001
            pass


def apply_print_options(printer: QPrinter, opts: PrintOptions) -> None:
    apply_margins(printer, opts.margin_mm)
    apply_duplex(printer, opts.duplex)


# ---------------------------------------------------------------- 打印机

def available_printers() -> list:
    """返回系统里的打印机列表（QPrinterInfo），没有则为空。"""
    from PySide6.QtPrintSupport import QPrinterInfo
    try:
        return list(QPrinterInfo.availablePrinters())
    except Exception:                                      # noqa: BLE001
        return []


def find_printer(name: str):
    from PySide6.QtPrintSupport import QPrinterInfo
    for info in available_printers():
        if info.printerName() == name:
            return info
    try:
        return QPrinterInfo.defaultPrinter()
    except Exception:                                      # noqa: BLE001
        return QPrinterInfo()


def make_printer(name: str = "", page_layout=None) -> QPrinter:
    """按名字造一个高分辨率 QPrinter；找不到就用系统默认打印机。"""
    info = find_printer(name) if name else find_printer("")
    printer = QPrinter(QPrinter.PrinterMode.HighResolution) if info is None or info.isNull() \
        else QPrinter(info, QPrinter.PrinterMode.HighResolution)
    if page_layout is not None:
        try:
            printer.setPageLayout(page_layout)
        except Exception:                                  # noqa: BLE001
            pass
    return printer


def ensure_a4(printer: QPrinter) -> None:
    """身份证打印固定用 A4 纵向；打印机默认是 Letter 之类时纠正过来。"""
    try:
        if printer.pageLayout().pageSize().id() == QPageSize.PageSizeId.A4:
            return
        printer.setPageLayout(QPageLayout(
            QPageSize(QPageSize.PageSizeId.A4),
            QPageLayout.Orientation.Portrait,
            QMarginsF(0, 0, 0, 0),
            QPageLayout.Unit.Millimeter))
    except Exception:                                      # noqa: BLE001
        pass


# ---------------------------------------------------------------- 绘制

def _caption_height(opts: PrintOptions, px_per_mm: float) -> float:
    if not opts.caption:
        return 0.0
    lines = 1 + (1 if (opts.show_title and opts.show_date) else 0)
    line_h = 3.6 * px_per_mm              # 约 10pt 行高
    return line_h * lines + 1.6 * px_per_mm


def _draw_cell(p: QPainter, cell: QRectF, item: PrintItem, opts: PrintOptions,
               px_per_mm: float) -> None:
    path = item.image
    if path is None or path.isNull():
        return

    cap_h = _caption_height(opts, px_per_mm)
    box = QRectF(cell.x(), cell.y(), cell.width(), max(1.0, cell.height() - cap_h))

    iw, ih = path.width(), path.height()
    if iw <= 0 or ih <= 0:
        return

    if opts.scale == "fill":
        k = max(box.width() / iw, box.height() / ih)
    elif opts.scale == "shrink":
        dpm = path.dotsPerMeterX()
        img_dpi = dpm / 25.4 if dpm > 0 else FALLBACK_DPI
        k = px_per_mm * 25.4 / img_dpi     # 1 画面像素对应多少画布像素
        k = min(k, box.width() / iw, box.height() / ih)
    else:
        k = min(box.width() / iw, box.height() / ih)

    w, h = iw * k, ih * k
    target = QRectF(box.center().x() - w / 2, box.center().y() - h / 2, w, h)

    p.save()
    if opts.scale == "fill":
        p.setClipRect(box)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    # 透明图（PNG / ICO）先铺白底，避免打印成黑块
    if path.hasAlphaChannel():
        p.fillRect(box.intersected(QRectF(target.x(), target.y(),
                                          target.width(), target.height())),
                   QColor("#ffffff"))
    p.drawImage(target, path)
    p.restore()

    if not opts.caption:
        return

    font = QFont(FONT_FAMILY)
    font.setPointSizeF(7.5)
    p.setFont(font)
    p.setPen(QColor("#333333"))
    fm = QFontMetricsF(font, p.device())
    # 图注紧贴图片下沿，图片较扁时不会飘到格子底部
    y = min(target.bottom() + 0.8 * px_per_mm, cell.bottom() - cap_h + 0.6 * px_per_mm)
    line_h = fm.height()
    inner_w = max(10.0, cell.width() - 1.0)

    if opts.show_title:
        title = item.title or ""
        text = fm.elidedText(title, Qt.TextElideMode.ElideMiddle, inner_w)
        p.drawText(QRectF(cell.x(), y, cell.width(), line_h),
                   int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
                   text)
        y += line_h
    if opts.show_date:
        font.setPointSizeF(6.8)
        p.setFont(font)
        p.setPen(QColor("#777777"))
        fm2 = QFontMetricsF(font, p.device())
        text = fm2.elidedText(item.date or "", Qt.TextElideMode.ElideRight, inner_w)
        p.drawText(QRectF(cell.x(), y, cell.width(), fm2.height()),
                   int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
                   text)


def paint_canvas(p: QPainter, canvas: QRectF, items: Sequence[PrintItem],
                 opts: PrintOptions, px_per_mm: float) -> None:
    """在 canvas 里排布一页的图像。canvas 单位是设备像素。"""
    if not items:
        return
    landscape = canvas.width() > canvas.height()
    cols, rows = grid_for(opts.per_page, landscape)
    gap = max(0.0, opts.gap_mm) * px_per_mm
    cw = (canvas.width() - gap * (cols - 1)) / cols
    ch = (canvas.height() - gap * (rows - 1)) / rows
    if cw <= 2 or ch <= 2:
        return
    for i, item in enumerate(items):
        r, c = divmod(i, cols)
        if r >= rows:
            break
        cell = QRectF(canvas.x() + c * (cw + gap), canvas.y() + r * (ch + gap), cw, ch)
        _draw_cell(p, cell, item, opts, px_per_mm)


# ---------------------------------------------------------------- 打印

def draw_document(printer: QPrinter, items: Sequence[PrintItem],
                  opts: PrintOptions, progress=None) -> int:
    """把全部图片按版面打到 printer，返回页数。progress(page, total) 可选。"""
    if not items:
        return 0
    apply_print_options(printer, opts)
    total = page_count(len(items), opts.per_page)
    per = max(1, int(opts.per_page))

    p = QPainter()
    if not p.begin(printer):
        raise RuntimeError("无法开始打印，请检查打印机状态")

    try:
        px_per_mm = printer.resolution() / 25.4
        canvas = canvas_rect(printer)
        for page in range(total):
            if page > 0 and not printer.newPage():
                break
            chunk = items[page * per:(page + 1) * per]
            paint_canvas(p, canvas, chunk, opts, px_per_mm)
            if progress is not None:
                progress(page + 1, total)
    finally:
        p.end()
    return total


def export_pdf(printer: QPrinter, path: str, items: Sequence[PrintItem],
               opts: PrintOptions) -> int:
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(path)
    return draw_document(printer, items, opts)


# ---------------------------------------------------------------- 预览

def printable_mm(printer: QPrinter) -> Tuple[float, float, float, float]:
    """真实可打印区的四边留白（mm）。小于硬件最小边距的设定会被打印机钳住，
    这里读回来，让预览和实际出纸完全一致。"""
    pw, ph = paper_mm(printer)
    r = printer.pageRect(QPrinter.Unit.Millimeter)
    if r.width() <= 0 or r.height() <= 0:
        return 0.0, 0.0, 0.0, 0.0
    mx = max(0.0, (pw - r.width()) / 2.0)
    my = max(0.0, (ph - r.height()) / 2.0)
    return mx, my, mx, my


def render_page(printer: QPrinter, margin_mm: float,
                max_px: Tuple[int, int] = (760, 900), paint=None) -> QImage:
    """把「一页纸」渲染成预览图：白纸 + 页边距虚线 + 内容。

    paint(p, canvas, px_per_mm) 负责画内容，canvas 是图片坐标系下的可打印区。
    打印、身份证排版等预览共用这套几何，保证预览和出纸一致。
    """
    pw, ph = paper_mm(printer)
    if pw <= 0 or ph <= 0:
        pw, ph = 210.0, 297.0
    scale = min(max_px[0] / pw, max_px[1] / ph)
    scale = max(0.6, min(scale, 4.0))

    w = max(2, int(round(pw * scale)))
    h = max(2, int(round(ph * scale)))
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.setDotsPerMeterX(int(scale * 1000))
    img.setDotsPerMeterY(int(scale * 1000))
    img.fill(QColor("#ffffff"))

    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    # 可打印区：纸张减去真实页边距（会把硬件最小边距算进去）
    apply_margins(printer, margin_mm)
    ml, mt, mr, mb = printable_mm(printer)
    canvas = QRectF(ml * scale, mt * scale,
                    w - (ml + mr) * scale, h - (mt + mb) * scale)
    if canvas.width() < 4 or canvas.height() < 4:
        canvas = QRectF(1, 1, w - 2, h - 2)

    # 页边距之外的淡淡提示线
    pen = QPen(QColor("#d7dce6"), 1, Qt.PenStyle.DashLine)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(canvas.adjusted(0.5, 0.5, -0.5, -0.5))

    if paint is not None:
        paint(p, canvas, scale)
    p.end()
    return img


def preview_image(printer: QPrinter, items: Sequence[PrintItem], opts: PrintOptions,
                  page: int, max_px: Tuple[int, int] = (760, 900)) -> QImage:
    """渲染某一页的预览图（含纸张白边与页边距示意），单位是图片像素。"""
    per = max(1, int(opts.per_page))
    chunk = list(items)[page * per:(page + 1) * per]
    return render_page(printer, opts.margin_mm, max_px,
                       lambda p, canvas, k: paint_canvas(p, canvas, chunk, opts, k))
