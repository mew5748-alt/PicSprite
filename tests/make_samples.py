# -*- coding: utf-8 -*-
"""生成一批测试图片（多种格式），用于功能自测与界面预览。"""
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "samples")


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def gradient(w, h, top, bottom):
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=lerp(top, bottom, y / max(1, h - 1)))
    return img


def scenery(seed=0):
    w, h = 2400, 1600
    sky_top = [(28, 52, 96), (96, 54, 92), (18, 46, 78)][seed % 3]
    sky_bot = [(246, 172, 116), (255, 206, 150), (168, 208, 226)][seed % 3]
    img = gradient(w, h, sky_top, sky_bot)
    d = ImageDraw.Draw(img, "RGBA")
    # 太阳
    d.ellipse([w * 0.62, h * 0.28, w * 0.82, h * 0.28 + w * 0.2],
              fill=(255, 236, 190, 210))
    img = img.filter(ImageFilter.GaussianBlur(1.2))
    d = ImageDraw.Draw(img, "RGBA")
    # 远山
    far = [(0, h)]
    for i in range(9):
        x = w * i / 8
        far.append((x, h * 0.58 + math.sin(i * 1.3 + seed) * h * 0.06))
    far.append((w, h))
    d.polygon(far, fill=(52, 62, 96, 235))
    # 近山
    near = [(0, h), (0, h * 0.74)]
    for i in range(7):
        x = w * i / 6
        near.append((x, h * 0.72 + math.cos(i * 1.9 + seed) * h * 0.08))
    near += [(w, h * 0.80), (w, h)]
    d.polygon(near, fill=(24, 30, 48, 255))
    # 水面
    d.rectangle([0, h * 0.86, w, h], fill=(40, 58, 92, 210))
    for i in range(22):
        y = h * 0.87 + i * (h * 0.12 / 22)
        x0 = w * (0.1 + 0.03 * math.sin(i))
        d.line([(x0, y), (x0 + w * (0.3 + 0.1 * math.cos(i)), y)],
               fill=(255, 220, 180, 40), width=2)
    return img


def city(seed=1):
    w, h = 1920, 1280
    img = gradient(w, h, (16, 24, 44), (72, 88, 130))
    d = ImageDraw.Draw(img, "RGBA")
    x = 0
    import random
    rnd = random.Random(seed)
    while x < w:
        bw = rnd.randint(90, 220)
        bh = rnd.randint(260, 820)
        top = h - bh
        shade = rnd.randint(18, 46)
        d.rectangle([x, top, x + bw, h], fill=(shade, shade + 6, shade + 20, 255))
        for wy in range(top + 24, h - 30, 34):
            for wx in range(x + 16, x + bw - 20, 30):
                if rnd.random() > 0.55:
                    d.rectangle([wx, wy, wx + 12, wy + 16],
                                fill=(255, 214, 138, rnd.randint(80, 220)))
        x += bw + rnd.randint(6, 26)
    d.rectangle([0, h - 40, w, h], fill=(10, 12, 22, 255))
    for i in range(30):
        d.line([(i * w / 29, h - 20), (i * w / 29 + 60, h - 20)],
               fill=(240, 230, 160, 60), width=3)
    return img


def flower():
    w = h = 1200
    img = gradient(w, h, (250, 246, 238), (226, 232, 220))
    d = ImageDraw.Draw(img, "RGBA")
    cx, cy = w / 2, h / 2
    for k in range(9):
        a = k * 40
        px = cx + math.cos(math.radians(a)) * 210
        py = cy + math.sin(math.radians(a)) * 210
        d.ellipse([px - 150, py - 150, px + 150, py + 150],
                  fill=(240, 122, 148, 90))
    for k in range(6):
        a = k * 60
        px = cx + math.cos(math.radians(a)) * 130
        py = cy + math.sin(math.radians(a)) * 130
        d.ellipse([px - 110, py - 110, px + 110, py + 110],
                  fill=(250, 176, 110, 120))
    d.ellipse([cx - 110, cy - 110, cx + 110, cy + 110], fill=(120, 70, 40, 255))
    img = img.filter(ImageFilter.GaussianBlur(3))
    d = ImageDraw.Draw(img, "RGBA")
    d.ellipse([cx - 70, cy - 70, cx + 70, cy + 70], fill=(86, 48, 28, 255))
    return img


def icon_art():
    s = 512
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    d.rounded_rectangle([24, 24, s - 24, s - 24], 92, fill=(47, 111, 237, 255))
    d.ellipse([s * 0.62, s * 0.2, s * 0.82, s * 0.4], fill=(255, 255, 255, 255))
    d.polygon([(80, 400), (210, 200), (300, 320), (370, 235), (440, 400)],
              fill=(255, 255, 255, 255))
    return img


def make_gif():
    frames = []
    w = h = 240
    for i in range(8):
        img = Image.new("RGB", (w, h), (245, 247, 250))
        d = ImageDraw.Draw(img)
        a = i * 45
        x = w / 2 + math.cos(math.radians(a)) * 70
        y = h / 2 + math.sin(math.radians(a)) * 70
        d.ellipse([x - 26, y - 26, x + 26, y + 26], fill=(47, 111, 237))
        d.ellipse([w / 2 - 12, h / 2 - 12, w / 2 + 12, h / 2 + 12], fill=(255, 120, 90))
        frames.append(img)
    return frames


def main():
    os.makedirs(OUT, exist_ok=True)
    a = scenery(0)
    a.save(os.path.join(OUT, "01 山间黄昏.jpg"), quality=92)
    b = city()
    b.save(os.path.join(OUT, "02 城市夜色.jpg"), quality=90)
    c = flower()
    c.save(os.path.join(OUT, "03 花朵特写.png"))
    icon_art().save(os.path.join(OUT, "04 应用图标.png"))
    a.resize((1600, 1067)).save(os.path.join(OUT, "05 扫描文档.tif"), compression="tiff_lzw")
    b.resize((1280, 853)).save(os.path.join(OUT, "06 作品.webp"), quality=88)
    gif = make_gif()
    gif[0].save(os.path.join(OUT, "07 动画.gif"), save_all=True, append_images=gif[1:],
                duration=90, loop=0)
    icon_art().save(os.path.join(OUT, "08 图标.ico"),
                    sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    c.resize((900, 900)).convert("RGB").save(os.path.join(OUT, "09 截图.bmp"))
    a.resize((1400, 933)).save(os.path.join(OUT, "10 长图.jpeg"), quality=80)
    print("已生成测试图片:", OUT, len(os.listdir(OUT)), "个文件")


if __name__ == "__main__":
    main()
