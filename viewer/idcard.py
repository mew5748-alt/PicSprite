# -*- coding: utf-8 -*-
"""身份证打印：自动找出卡片边界、裁成 85.6 × 54 mm，再按实际尺寸排到 A4 上。

自动裁剪的思路（照片里的卡片通常是「浅色矩形」）：
  1. 缩到 400 px 左右做分析，先做边缘图；
  2. 候选一：Otsu 亮区连通域 —— 卡片比桌面亮，这一步最常见也最准；
  3. 候选二：封闭轮廓 —— 边缘连成一圈把里面围住，适合白纸上的卡片；
  4. 每个候选把四条边向外/向内微调到边缘最强处，再按
     「边缘支撑度 + 长宽比 + 面积占比」打分，取最高分；
  5. 分数不够就退回「居中按卡片比例裁剪」，并标记为需要人工确认。
坐标全部按源图像素记录，裁剪交给 Pillow 绕卡片中心旋转，避免坐标漂移。
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageFilter
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtPrintSupport import QPrinter

from . import imageio, printing

CARD_W_MM = 85.6
CARD_H_MM = 54.0
CARD_RATIO = CARD_W_MM / CARD_H_MM
MAX_SIDE = 400


@dataclass
class CardBox:
    """卡片位置。cx/cy 为中心，w/h 沿卡片自身方向，angle 为倾斜角（度）。"""

    cx: float
    cy: float
    w: float
    h: float
    angle: float = 0.0
    confidence: float = 0.0
    auto: bool = True

    def bounds(self) -> QRectF:
        """外接矩形（源图像素）。"""
        a = math.radians(self.angle)
        bw = abs(self.w * math.cos(a)) + abs(self.h * math.sin(a))
        bh = abs(self.w * math.sin(a)) + abs(self.h * math.cos(a))
        return QRectF(self.cx - bw / 2, self.cy - bh / 2, bw, bh)


# ---------------------------------------------------------------- 几何工具

def _min_area_rect(points: Sequence[Tuple[float, float]]):
    """点集的最小外接矩形（凸包 + 旋转卡壳），返回 4 个角点。"""
    pts = sorted(set((round(x, 2), round(y, 2)) for x, y in points))
    if len(pts) < 3:
        return None

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: List[Tuple[float, float]] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: List[Tuple[float, float]] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    if len(hull) < 3:
        return None

    best = None
    n = len(hull)
    for i in range(n):
        x1, y1 = hull[i]
        x2, y2 = hull[(i + 1) % n]
        dx, dy = x2 - x1, y2 - y1
        ln = math.hypot(dx, dy)
        if ln < 1e-6:
            continue
        ux, uy = dx / ln, dy / ln
        us = [px * ux + py * uy for px, py in hull]
        vs = [-px * uy + py * ux for px, py in hull]
        area = (max(us) - min(us)) * (max(vs) - min(vs))
        if best is None or area < best[0]:
            best = (area, ux, uy, min(us), max(us), min(vs), max(vs))
    if best is None:
        return None
    _a, ux, uy, minu, maxu, minv, maxv = best
    return [(u * ux - v * uy, u * uy + v * ux)
            for u, v in ((minu, minv), (maxu, minv), (maxu, maxv), (minu, maxv))]


def _box_from_corners(corners) -> CardBox:
    p0, p1, p2, _p3 = corners
    e1 = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    e2 = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    cx = sum(p[0] for p in corners) / 4.0
    cy = sum(p[1] for p in corners) / 4.0
    if e1 >= e2:
        ang = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
        w, h = e1, e2
    else:
        ang = math.degrees(math.atan2(p2[1] - p1[1], p2[0] - p1[0]))
        w, h = e2, e1
    while ang > 90:
        ang -= 180
    while ang < -90:
        ang += 180
    return CardBox(cx, cy, w, h, ang)


def _components(mask, w: int, h: int, min_px: int = 30) -> List[List[int]]:
    """4 连通域（只走 1 像素），返回按面积降序的点下标列表。"""
    pool = {i for i, v in enumerate(mask) if v}
    comps: List[List[int]] = []
    while pool:
        start = pool.pop()
        comp = [start]
        q = deque([start])
        while q:
            i = q.popleft()
            x = i % w
            for j in (i - 1, i + 1, i - w, i + w):
                if j in pool and not ((j == i - 1 and x == 0) or (j == i + 1 and x == w - 1)):
                    pool.discard(j)
                    comp.append(j)
                    q.append(j)
        if len(comp) >= min_px:
            comps.append(comp)
    comps.sort(key=len, reverse=True)
    return comps


def _otsu(gray: bytes) -> int:
    hist = [0] * 256
    for v in gray:
        hist[v] += 1
    total = len(gray)
    total_sum = sum(i * hist[i] for i in range(256))
    best_t, best_var = 128, -1.0
    wb = sb = 0
    for t in range(256):
        wb += hist[t]
        if wb == 0:
            continue
        wf = total - wb
        if wf == 0:
            break
        sb += t * hist[t]
        mb = sb / wb
        mf = (total_sum - sb) / wf
        var = wb * wf * (mb - mf) ** 2
        if var > best_var:
            best_var, best_t = var, t
    return best_t


def _edge_support(ed: bytes, w: int, h: int, box: CardBox, thr: int, radius: int = 4,
                  steps: int = 32) -> float:
    """四条边上「能找到强边缘」的比例，0~1。用来判断这个矩形是不是卡片的真实边界。"""
    if box.w < 4 or box.h < 4:
        return 0.0
    a = math.radians(box.angle)
    ux, uy = math.cos(a), math.sin(a)
    vx, vy = -uy, ux
    hit = tot = 0
    for side in (0, 1):
        for t in range(steps + 1):
            f = t / steps - 0.5
            for sgn in (-0.5, 0.5):
                if side == 0:
                    x = box.cx + f * box.w * ux + sgn * box.h * vx
                    y = box.cy + f * box.w * uy + sgn * box.h * vy
                else:
                    x = box.cx + f * box.h * vx + sgn * box.w * ux
                    y = box.cy + f * box.h * vy + sgn * box.w * uy
                tot += 1
                xi, yi = int(x), int(y)
                ok = False
                for dy in range(-radius, radius + 1):
                    yy = yi + dy
                    if yy < 0 or yy >= h:
                        continue
                    row = yy * w
                    for dx in range(-radius, radius + 1):
                        xx = xi + dx
                        if 0 <= xx < w and ed[row + xx] >= thr:
                            ok = True
                            break
                    if ok:
                        break
                hit += 1 if ok else 0
    return hit / max(1, tot)


def _refine_angle(ed: bytes, w: int, h: int, box: CardBox, thr: int) -> CardBox:
    """估计卡片倾斜角：在 ±10° 内找一个让四条边最贴合边缘的角度。"""
    def score(deg: float) -> float:
        cand = CardBox(box.cx, box.cy, box.w, box.h, deg)
        return _edge_support(ed, w, h, cand, thr, radius=2, steps=10)

    best_deg, best_s = box.angle, score(box.angle)
    deg = -10.0
    while deg <= 10.0:
        s = score(deg)
        if s > best_s + 0.02:
            best_deg, best_s = deg, s
        deg += 2.0
    # 再在附近细化半步
    for d in (-1.0, -0.5, 0.5, 1.0):
        s = score(best_deg + d)
        if s > best_s:
            best_deg, best_s = best_deg + d, s
    return CardBox(box.cx, box.cy, box.w, box.h, best_deg, confidence=box.confidence)


def _refine_box(ed: bytes, w: int, h: int, box: CardBox, reach: int = 5) -> CardBox:
    """把四条边各自微调到边缘响应最强的位置，让框贴合真实卡片边。"""
    a = math.radians(box.angle)
    ux, uy = math.cos(a), math.sin(a)
    vx, vy = -uy, ux

    def line_score(offset: float, side: int) -> float:
        total = 0.0
        n = 0
        for t in range(9):
            f = t / 8 - 0.5
            if side == 0:
                x = box.cx + f * box.w * ux + offset * vx
                y = box.cy + f * box.w * uy + offset * vy
            else:
                x = box.cx + f * box.h * vx + offset * ux
                y = box.cy + f * box.h * vy + offset * uy
            xi, yi = int(round(x)), int(round(y))
            best = 0
            for dy in (-1, 0, 1):
                yy = yi + dy
                if 0 <= yy < h:
                    row = yy * w
                    for dx in (-1, 0, 1):
                        xx = xi + dx
                        if 0 <= xx < w:
                            best = max(best, ed[row + xx])
            total += best
            n += 1
        return total / max(1, n)

    def best_offset(base: float, side: int) -> float:
        scores = [(line_score(base + d * 0.5, side), base + d * 0.5)
                  for d in range(-2 * reach, 2 * reach + 1)]
        scores.sort(key=lambda s: -s[0])
        return scores[0][1]

    # 上下边（沿 v 方向偏移）与左右边（沿 u 方向偏移）各调一次
    new_h = box.h
    top = best_offset(-box.h / 2, 0)
    bottom = best_offset(box.h / 2, 0)
    new_w = box.w
    left = best_offset(-box.w / 2, 1)
    right = best_offset(box.w / 2, 1)
    if bottom - top > 6:
        new_h = (bottom - top) / 2
        shift_v = (bottom + top) / 2
    else:
        shift_v = 0.0
    if right - left > 6:
        new_w = (right - left) / 2
        shift_u = (right + left) / 2
    else:
        shift_u = 0.0
    return CardBox(box.cx + shift_u * ux + shift_v * vx,
                   box.cy + shift_u * uy + shift_v * vy,
                   new_w * 2, new_h * 2, box.angle, confidence=box.confidence)


# ---------------------------------------------------------------- 识别

def _to_gray(qimg: QImage) -> Tuple[Image.Image, Image.Image, float]:
    """返回 (轻微模糊的灰度图, 原始灰度图, 缩放比)。模糊图用来找边缘，原图用来找内容反差。"""
    pil = imageio.pil_from_qimage(qimg).convert("L")
    scale = min(1.0, MAX_SIDE / max(pil.width, pil.height))
    w = max(1, int(round(pil.width * scale)))
    h = max(1, int(round(pil.height * scale)))
    small = pil.resize((w, h), Image.BILINEAR)
    return small.filter(ImageFilter.GaussianBlur(1.0)), small, scale


def _content_box(gray_img: Image.Image, w: int, h: int) -> Optional[CardBox]:
    """高通滤波后「和周围不一样」的像素就是卡片内容，取其最小外接矩形。

    卡片本身可能是白底白边，只靠亮度分不开，但它的边框、文字、阴影一定和周围有反差，
    这一步能同时拿到位置和倾斜角。
    """
    from PIL import ImageChops

    hp = ImageChops.difference(gray_img, gray_img.filter(ImageFilter.GaussianBlur(10)))
    data = hp.tobytes()
    vals = sorted(data)
    thr = max(8, vals[int(len(vals) * 0.90)])
    mask = bytearray(1 if v >= thr else 0 for v in data)
    comps = _components(mask, w, h, int(w * h * 0.01))
    if not comps:
        return None
    main = comps[0]
    xs = [i % w for i in main]
    ys = [i // w for i in main]
    pad_x = max(2, int((max(xs) - min(xs)) * 0.04))
    pad_y = max(2, int((max(ys) - min(ys)) * 0.04))
    x0, x1 = min(xs) - pad_x, max(xs) + pad_x
    y0, y1 = min(ys) - pad_y, max(ys) + pad_y
    pts = [(i % w, i // w) for i in range(w * h)
           if mask[i] and x0 <= i % w <= x1 and y0 <= i // w <= y1]
    if len(pts) < 60:
        return None
    corners = _min_area_rect(pts)
    return _box_from_corners(corners) if corners else None


def _score(box: CardBox, w: int, h: int, ed: bytes, thr: int, gray: bytes) -> float:
    ratio = max(box.w, box.h) / max(1e-6, min(box.w, box.h))
    frac = (box.w * box.h) / max(1.0, w * h)
    s_ratio = max(0.0, 1.0 - abs(ratio - CARD_RATIO) / 0.55)
    s_area = min(1.0, frac / 0.12) * (1.0 if frac <= 1.02 else 0.6)
    s_edge = _edge_support(ed, w, h, box, thr)
    # 卡片内部应当偏亮
    s_bright = 1.0
    try:
        rx = box.bounds().toRect() if hasattr(box.bounds(), "toRect") else None
        x0 = max(0, int(box.cx - box.w / 2)); x1 = min(w, int(box.cx + box.w / 2))
        y0 = max(0, int(box.cy - box.h / 2)); y1 = min(h, int(box.cy + box.h / 2))
        if x1 > x0 + 2 and y1 > y0 + 2:
            step_x = max(1, (x1 - x0) // 12)
            step_y = max(1, (y1 - y0) // 12)
            vals = [gray[y * w + x]
                    for y in range(y0, y1, step_y) for x in range(x0, x1, step_x)]
            mean_in = sum(vals) / len(vals) if vals else 0
            s_bright = min(1.0, mean_in / 190.0) * 0.5 + 0.5
    except Exception:                                      # noqa: BLE001
        s_bright = 0.8
    return 0.55 * s_edge + 0.27 * s_ratio + 0.11 * s_area + 0.07 * s_bright


def detect_card_box(qimg: QImage) -> CardBox:
    """识别卡片位置。识别不出来返回居中等比的框，auto=False。"""
    W, H = qimg.width(), qimg.height()
    if W < 40 or H < 40:
        return center_box(qimg)

    gray_img, raw_img, scale = _to_gray(qimg)
    w, h = gray_img.size
    gray = gray_img.tobytes()

    ed_img = gray_img.filter(ImageFilter.FIND_EDGES)
    ed = bytearray(ed_img.tobytes())
    # FIND_EDGES 把图像最外圈也当边缘，会让泛洪没有种子、也会让「整图框」得分虚高
    for d in range(2):
        for x in range(w):
            ed[d * w + x] = 0
            ed[(h - 1 - d) * w + x] = 0
        for y in range(h):
            ed[y * w + d] = 0
            ed[y * w + w - 1 - d] = 0
    ed = bytes(ed)
    vals = sorted(ed)
    thr = max(24, vals[int(len(vals) * 0.965)])

    emask = bytearray(1 if v >= thr else 0
                      for v in ed_img.point(lambda v: 255 if v >= thr else 0)
                      .filter(ImageFilter.MaxFilter(3)).tobytes())
    # FIND_EDGES 把图像最外圈也当边缘，会让泛洪没有种子，先清掉两圈
    for d in range(2):
        for x in range(w):
            emask[d * w + x] = 0
            emask[(h - 1 - d) * w + x] = 0
        for y in range(h):
            emask[y * w + d] = 0
            emask[y * w + w - 1 - d] = 0

    cands: List[Tuple[str, CardBox]] = []

    # 一、已经是卡片比例（扫描件 / 裁好的图）就直接整图
    if min(abs((W / H) / CARD_RATIO - 1), abs((H / W) / CARD_RATIO - 1)) < 0.05:
        return CardBox(W / 2, H / 2, W, H, 0.0, 1.0, auto=True)

    # 二、封闭轮廓：边缘围成一圈，里面泛洪到不了
    reach = bytearray(w * h)
    q = deque()
    for x in range(w):
        for y in (1, h - 2):
            i = y * w + x
            if not emask[i] and not reach[i]:
                reach[i] = 1
                q.append(i)
    while q:
        i = q.popleft()
        x = i % w
        for j in (i - 1, i + 1, i - w, i + w):
            if j < 0 or j >= w * h or reach[j] or emask[j]:
                continue
            if (j == i - 1 and x == 0) or (j == i + 1 and x == w - 1):
                continue
            reach[j] = 1
            q.append(j)
    enclosed = bytearray(1 if (not emask[i] and not reach[i]) else 0 for i in range(w * h))
    for comp in _components(enclosed, w, h, int(w * h * 0.06))[:2]:
        pts = [(i % w, i // w) for i in comp]
        corners = _min_area_rect(pts)
        if corners:
            cands.append(("enclosed", _box_from_corners(corners)))

    # 三、亮区连通域
    t = _otsu(gray)
    bright = bytearray(1 if v > t else 0 for v in gray)
    bimg = Image.frombytes("L", (w, h), bytes(bright)).filter(ImageFilter.MaxFilter(3))
    bright = bytearray(1 if v else 0 for v in bimg.tobytes())
    for comp in _components(bright, w, h, int(w * h * 0.05))[:3]:
        corners = _min_area_rect([(i % w, i // w) for i in comp])
        if corners:
            cands.append(("bright", _box_from_corners(corners)))

    # 四、高通内容块（白底卡片也能抓住，且带倾斜角）
    content = _content_box(raw_img, w, h)
    if content is not None:
        cands.append(("content", content))


    best: Optional[CardBox] = None
    best_score = -1.0
    best_src = ""
    for src, box in cands:
        refined = _refine_box(ed, w, h, box)
        # 边框很淡时「凑边缘」会把框缩到文字上，缩太多就保留原框
        if refined.w * refined.h < 0.8 * box.w * box.h:
            refined = box
        # 几乎盖满整幅画面的框说明「没找到卡片」，直接丢掉
        if (refined.w * refined.h) / float(w * h) >= 0.92:
            continue
        s = _score(refined, w, h, ed, thr, gray)
        if s > best_score:
            best, best_score, best_src = refined, s, src

    # 「内容块」这条线索本身就说明画面里有明确边界，门槛可以低一点
    limit = 0.42 if best_src == "content" else 0.55
    if best is None or best_score < limit:
        return center_box(qimg)

    # 回到源图坐标。不做比例硬锁：多出来的边（阴影/白边）交给排版时的「铺满」裁掉，
    # 这样比强行拉伸更不容易切到证件内容。
    k = 1.0 / scale
    return CardBox(best.cx * k, best.cy * k, best.w * k, best.h * k, best.angle,
                   confidence=min(1.0, max(0.0, best_score)), auto=True)


def center_box(qimg: QImage) -> CardBox:
    """居中等比裁剪：在画面里取最大的 85.6:54 区域。"""
    W, H = max(1, qimg.width()), max(1, qimg.height())
    if W / H >= CARD_RATIO:
        bw, bh = H * CARD_RATIO, float(H)
    else:
        bw, bh = float(W), W / CARD_RATIO
    # 留一点余量，避免把画面外的黑边带进来
    bw *= 0.985
    bh *= 0.985
    return CardBox(W / 2, H / 2, bw, bh, 0.0, 0.0, auto=False)


def crop_card(qimg: QImage, box: CardBox, max_side: int = 2600) -> QImage:
    """按 CardBox 裁剪出卡片；倾斜的先转正，竖版再转成横版。"""
    if qimg.isNull():
        return qimg
    pil = imageio.pil_from_qimage(qimg).convert("RGB")
    W, H = pil.size
    if abs(box.angle) > 0.15:
        # Pillow 的 rotate 是逆时针，屏幕坐标 y 向下，所以取正角度转正
        pil = pil.rotate(box.angle, center=(box.cx, box.cy),
                         resample=Image.BICUBIC, expand=False)
    x0 = int(round(box.cx - box.w / 2))
    y0 = int(round(box.cy - box.h / 2))
    x1 = int(round(box.cx + box.w / 2))
    y1 = int(round(box.cy + box.h / 2))
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return qimg
    crop = pil.crop((x0, y0, x1, y1))
    if crop.width < crop.height:
        crop = crop.rotate(-90, expand=True)
    if max(crop.size) > max_side:
        crop.thumbnail((max_side, max_side), Image.LANCZOS)
    return imageio.qimage_from_pil(crop)


def auto_crop(qimg: QImage) -> Tuple[QImage, CardBox]:
    box = detect_card_box(qimg)
    return crop_card(qimg, box), box


# ---------------------------------------------------------------- 版面

@dataclass
class IdCardOptions:
    layout: str = "vertical"          # vertical（上下）| horizontal（左右）
    gap_mm: float = 18.0
    margin_mm: float = 10.0
    border: bool = False
    copies: int = 1
    duplex: str = "none"
    printer_name: str = ""


def slots(canvas: QRectF, opts: IdCardOptions, px_per_mm: float,
          has_front: bool, has_back: bool) -> List[Tuple[QRectF, str]]:
    """返回 [(卡片矩形, "front"/"back")]。"""
    cw = CARD_W_MM * px_per_mm
    ch = CARD_H_MM * px_per_mm
    gap = max(0.0, opts.gap_mm) * px_per_mm

    if has_front and has_back:
        if opts.layout == "horizontal":
            # 两张横着放不下时，先把间距压小；实在放不下就改成上下排列
            if canvas.width() < cw * 2 + gap:
                gap = max(0.0, canvas.width() - cw * 2)
            if canvas.width() < cw * 2:
                opts = IdCardOptions(**{**vars(opts), "layout": "vertical"})
                return slots(canvas, opts, px_per_mm, has_front, has_back)
            total_w = cw * 2 + gap
            x = canvas.center().x() - total_w / 2
            y = canvas.center().y() - ch / 2
            return [(QRectF(x, y, cw, ch), "front"),
                    (QRectF(x + cw + gap, y, cw, ch), "back")]
        gap = min(gap, max(0.0, canvas.height() - ch * 2))
        total_h = ch * 2 + gap
        y = canvas.center().y() - total_h / 2
        x = canvas.center().x() - cw / 2
        return [(QRectF(x, y, cw, ch), "front"),
                (QRectF(x, y + ch + gap, cw, ch), "back")]

    one = "front" if has_front else "back"
    return [(QRectF(canvas.center().x() - cw / 2, canvas.center().y() - ch / 2, cw, ch), one)]


def _draw_card(p: QPainter, rect: QRectF, img: Optional[QImage],
               opts: IdCardOptions, px_per_mm: float) -> None:
    p.save()
    p.setClipRect(rect)
    p.fillRect(rect, QColor("#ffffff"))
    if img is not None and not img.isNull():
        # 源图已经裁成卡片比例，这里按「铺满」绘制，多出来的阴影/白边正好被裁掉；
        # 比例差太多时改为完整显示，避免切到证件内容。
        iw, ih = img.width(), img.height()
        src_ratio = iw / max(1, ih)
        if abs(src_ratio - CARD_RATIO) / CARD_RATIO <= 0.12:
            k = max(rect.width() / iw, rect.height() / ih)
        else:
            k = min(rect.width() / iw, rect.height() / ih)
        w, h = iw * k, ih * k
        target = QRectF(rect.center().x() - w / 2, rect.center().y() - h / 2, w, h)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p.drawImage(target, img)
    p.restore()
    if opts.border:
        pen = QPen(QColor("#c9ced8"))
        pen.setWidthF(max(0.8, 0.16 * px_per_mm))
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(rect.adjusted(0, 0, -0.001, -0.001))


def paint_page(p: QPainter, canvas: QRectF, front: Optional[QImage],
               back: Optional[QImage], opts: IdCardOptions, px_per_mm: float) -> None:
    for rect, which in slots(canvas, opts, px_per_mm, front is not None, back is not None):
        _draw_card(p, rect, front if which == "front" else back, opts, px_per_mm)


# ---------------------------------------------------------------- 打印 / 预览

def draw_document(printer: QPrinter, front: Optional[QImage], back: Optional[QImage],
                  opts: IdCardOptions) -> int:
    if front is None and back is None:
        return 0
    printing.apply_margins(printer, opts.margin_mm)
    printing.apply_duplex(printer, opts.duplex)
    copies = max(1, min(20, int(opts.copies or 1)))

    p = QPainter()
    if not p.begin(printer):
        raise RuntimeError("无法开始打印，请检查打印机状态")
    try:
        px_per_mm = printer.resolution() / 25.4
        canvas = printing.canvas_rect(printer)
        for i in range(copies):
            if i and not printer.newPage():
                break
            paint_page(p, canvas, front, back, opts, px_per_mm)
    finally:
        p.end()
    return copies


def export_pdf(printer: QPrinter, path: str, front: Optional[QImage],
               back: Optional[QImage], opts: IdCardOptions) -> int:
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(path)
    return draw_document(printer, front, back, opts)


def preview(printer: QPrinter, front: Optional[QImage], back: Optional[QImage],
            opts: IdCardOptions, max_px: Tuple[int, int] = (760, 900)) -> QImage:
    return printing.render_page(
        printer, opts.margin_mm, max_px,
        lambda p, canvas, k: paint_page(p, canvas, front, back, opts, k))
