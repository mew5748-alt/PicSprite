# -*- coding: utf-8 -*-
"""生成身份证样本图（用于裁剪算法与打印测试）。"""
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "samples")


def card_image(w=856, h=540, back=False):
    im = Image.new("RGB", (w, h), (246, 246, 242))
    d = ImageDraw.Draw(im)
    # 底纹
    for i in range(0, w, 24):
        d.line([(i, 0), (i - h, h)], fill=(238, 240, 236), width=1)
    d.rectangle([0, 0, w - 1, h - 1], outline=(214, 216, 210), width=3)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 34)
        big = ImageFont.truetype("C:/Windows/Fonts/msyhbd.ttc", 40)
    except Exception:
        font = big = ImageFont.load_default()
    if back:
        # 真实的国徽面：国徽在左上，红色标题在其右侧，下方是签发机关与有效期
        d.ellipse((70, 110, 260, 300), outline=(190, 46, 46), width=9)
        d.ellipse((108, 148, 222, 262), outline=(206, 66, 60), width=4)
        d.text((300, 150), "中华人民共和国", font=big, fill=(198, 48, 48))
        d.text((300, 218), "居民身份证", font=big, fill=(60, 60, 60))
        d.text((70, 370), "签发机关  某某市公安局", font=font, fill=(70, 70, 70))
        d.text((70, 440), "有效期限  2018.01.01-2038.01.01", font=font, fill=(70, 70, 70))
    else:
        d.text((60, 40), "姓名  张小明", font=big, fill=(40, 40, 40))
        d.text((60, 110), "性别  男    民族  汉", font=font, fill=(60, 60, 60))
        d.text((60, 175), "出生  1990 年 1 月 1 日", font=font, fill=(60, 60, 60))
        d.text((60, 245), "住址  某某省某某市某某区", font=font, fill=(60, 60, 60))
        d.text((60, 305), "      某某路 123 号 4 单元", font=font, fill=(60, 60, 60))
        d.text((60, 400), "公民身份号码  110101199001011234", font=font, fill=(40, 40, 40))
        d.rectangle([w - 260, 60, w - 60, 380], fill=(226, 232, 238))
        d.ellipse([w - 225, 100, w - 95, 230], fill=(196, 205, 214))
        d.polygon([(w - 245, 370), (w - 245, 260), (w - 185, 205),
                   (w - 130, 205), (w - 75, 260), (w - 75, 370)], fill=(170, 182, 196))
    return im


def desk(w, h, dark=(120, 96, 74)):
    im = Image.new("RGB", (w, h), dark)
    d = ImageDraw.Draw(im)
    random.seed(7)
    for y in range(0, h, 9):
        c = tuple(min(255, max(0, v + random.randint(-9, 9))) for v in dark)
        d.line([(0, y), (w, y + random.randint(-2, 2))], fill=c)
    return im.filter(ImageFilter.GaussianBlur(1.2))


def place(bg, card, angle, cx, cy, scale=1.0):
    c = card.resize((int(card.width * scale), int(card.height * scale)), Image.LANCZOS)
    c = c.convert("RGBA").rotate(angle, expand=True, resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0))
    # 阴影：真实拍摄时卡片边缘会投出一条明显的暗边，卡片边界主要靠它才能看到
    sh = Image.new("RGBA", (c.width + 40, c.height + 40), (0, 0, 0, 0))
    sh.paste(Image.new("RGBA", c.size, (0, 0, 0, 150)), (20, 20), c)
    sh = sh.filter(ImageFilter.GaussianBlur(4))
    bg.paste(sh, (int(cx - c.width / 2 - 20 + 6), int(cy - c.height / 2 - 20 + 8)), sh)
    bg.paste(c, (int(cx - c.width / 2), int(cy - c.height / 2)), c)


def main():
    os.makedirs(OUT, exist_ok=True)
    # 1. 桌面上的正面，轻微倾斜
    bg = desk(1600, 1200)
    place(bg, card_image(), 6, 800, 600)
    bg.save(os.path.join(OUT, "id-front.jpg"), quality=92)

    # 2. 白纸上拍的反面
    bg = Image.new("RGB", (1500, 1000), (250, 250, 248))
    d = ImageDraw.Draw(bg)
    # 纸张的自然明暗变化（不是画边框线）
    for i in range(0, 1000, 4):
        shade = 250 - int(6 * (i / 1000.0) ** 2)
        d.line([(0, i), (1499, i)], fill=(shade, shade, shade - 2))
    place(bg, card_image(back=True), -4, 750, 500, 0.95)
    bg.save(os.path.join(OUT, "id-back.jpg"), quality=92)

    # 3. 已经裁好的卡片（扫描件，填满画面）
    card_image().save(os.path.join(OUT, "id-flat.jpg"), quality=92)

    # 4. 空白桌面（没有卡片，测回退）
    desk(1400, 1000).save(os.path.join(OUT, "id-empty.jpg"), quality=90)
    print("已生成:", sorted(f for f in os.listdir(OUT) if f.startswith("id-")))


if __name__ == "__main__":
    main()
