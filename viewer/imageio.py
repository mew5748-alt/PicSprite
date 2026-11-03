# -*- coding: utf-8 -*-
"""图像读写、格式转换、缩放、编码体积控制。"""
from __future__ import annotations

import io
import os
import tempfile
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageFile, ImageOps, ImageSequence
from PySide6.QtGui import QImage

ImageFile.LOAD_TRUNCATED_IMAGES = True
try:
    Image.MAX_IMAGE_PIXELS = None          # 允许超大图（用户自己的图片）
except Exception:
    pass

LANCZOS = getattr(Image, "Resampling", Image).LANCZOS
NEAREST = getattr(Image, "Resampling", Image).NEAREST
BICUBIC = getattr(Image, "Resampling", Image).BICUBIC

# ---------------------------------------------------------------- 格式登记

READABLE_EXTS = [
    ".bmp", ".dib", ".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".ico", ".cur",
    ".tif", ".tiff", ".gif", ".webp", ".tga", ".ppm", ".pgm", ".pbm", ".pcx",
    ".dds", ".jp2", ".j2k", ".avif", ".heic", ".heif", ".psd", ".sgi", ".xbm",
]


@dataclass
class FormatSpec:
    key: str            # Pillow 格式名
    label: str          # 界面显示
    ext: str            # 默认扩展名
    quality: bool       # 是否支持质量参数
    alpha: bool         # 是否支持透明通道
    multi: bool = False


WRITE_FORMATS: List[FormatSpec] = [
    FormatSpec("JPEG", "JPG / JPEG（照片首选，体积小）", ".jpg", True, False),
    FormatSpec("PNG", "PNG（无损，支持透明）", ".png", False, True),
    FormatSpec("WEBP", "WebP（同画质体积更小）", ".webp", True, True),
    FormatSpec("BMP", "BMP（无压缩位图）", ".bmp", False, False),
    FormatSpec("TIFF", "TIFF（印刷存档）", ".tif", False, True, True),
    FormatSpec("GIF", "GIF（最多 256 色）", ".gif", False, False),
    FormatSpec("ICO", "ICO（Windows 图标）", ".ico", False, True, True),
]
FORMAT_BY_KEY: Dict[str, FormatSpec] = {f.key: f for f in WRITE_FORMATS}

FMT_LABEL = {
    "JPEG": "JPG", "MPO": "JPG", "PNG": "PNG", "GIF": "GIF", "BMP": "BMP",
    "TIFF": "TIFF", "WEBP": "WebP", "ICO": "ICO", "CUR": "CUR", "TGA": "TGA",
    "PCX": "PCX", "DDS": "DDS", "JPEG2000": "JP2", "AVIF": "AVIF", "PSD": "PSD",
}

EXIF_TAGS = {
    271: "制造商", 272: "型号", 305: "软件", 306: "修改时间",
    33434: "曝光时间", 33437: "光圈", 34855: "ISO", 37386: "焦距",
    36867: "拍摄时间", 36868: "数字化时间", 42036: "镜头",
}


def is_image_file(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in READABLE_EXTS


def format_label(path_or_fmt: str) -> str:
    ext = os.path.splitext(path_or_fmt)[1].lower()
    if ext:
        mapping = {".jpg": "JPG", ".jpeg": "JPG", ".jpe": "JPG", ".jfif": "JPG",
                   ".tif": "TIFF", ".tiff": "TIFF", ".ico": "ICO", ".cur": "CUR",
                   ".webp": "WebP", ".bmp": "BMP", ".png": "PNG", ".gif": "GIF",
                   ".tga": "TGA", ".jp2": "JP2", ".avif": "AVIF", ".psd": "PSD"}
        return mapping.get(ext, ext.lstrip(".").upper())
    return FMT_LABEL.get(path_or_fmt.upper(), path_or_fmt)


# ---------------------------------------------------------------- QImage <-> PIL

def qimage_from_pil(im: Image.Image) -> QImage:
    if im.mode == "RGB":
        data = im.tobytes("raw", "RGB")
        q = QImage(data, im.width, im.height, im.width * 3, QImage.Format.Format_RGB888)
        return q.copy()
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    data = im.tobytes("raw", "RGBA")
    q = QImage(data, im.width, im.height, im.width * 4, QImage.Format.Format_RGBA8888)
    return q.copy()


def pil_from_qimage(q: QImage) -> Image.Image:
    if q.isNull():
        raise ValueError("图像为空")
    q2 = q.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h, bpl = q2.width(), q2.height(), q2.bytesPerLine()
    data = bytes(q2.constBits())
    im = Image.frombuffer("RGBA", (w, h), data, "raw", "RGBA", bpl, 1)
    return im.copy()


# ---------------------------------------------------------------- 载入

@dataclass
class LoadedImage:
    path: str = ""
    image: Optional[QImage] = None
    frames: List[QImage] = field(default_factory=list)
    fmt: str = ""
    mode: str = "RGB"
    file_size: int = 0
    mtime: float = 0.0
    exif: Dict[str, str] = field(default_factory=dict)
    exif_bytes: Optional[bytes] = None
    icc: Optional[bytes] = None
    error: str = ""
    is_vector: bool = False

    @property
    def width(self) -> int:
        return self.image.width() if self.image is not None else 0

    @property
    def height(self) -> int:
        return self.image.height() if self.image is not None else 0


def _exif_summary(im: Image.Image) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        ex = im.getexif()
        if not ex:
            return out
        for tag, name in EXIF_TAGS.items():
            v = ex.get(tag)
            if v is None:
                continue
            if isinstance(v, bytes):
                try:
                    v = v.decode("utf-8", "ignore").strip("\x00")
                except Exception:
                    v = str(v)
            if isinstance(v, float):
                v = round(v, 3)
            out[name] = str(v)
        # 曝光时间美化
        if "曝光时间" in out:
            try:
                val = float(out["曝光时间"])
                if 0 < val < 1:
                    out["曝光时间"] = f"1/{round(1 / val)} 秒"
                else:
                    out["曝光时间"] = f"{val:g} 秒"
            except Exception:
                pass
        if "光圈" in out:
            try:
                out["光圈"] = f"f/{float(out['光圈']):g}"
            except Exception:
                pass
        if "焦距" in out:
            try:
                out["焦距"] = f"{float(out['焦距']):g} mm"
            except Exception:
                pass
    except Exception:
        pass
    return out


def _gif_frames(path: str, limit: int) -> List[QImage]:
    """用 QMovie 合成 GIF 帧（处理 disposal，效果比 PIL 直接转换准）。"""
    try:
        from PySide6.QtGui import QMovie, QPixmap
        movie = QMovie(path)
        if not movie.isValid():
            return []
        count = movie.frameCount()
        frames: List[QImage] = []
        if count <= 0 or count > limit:
            return []
        for i in range(count):
            movie.jumpToFrame(i)
            pm: QPixmap = movie.currentPixmap()
            if not pm.isNull():
                frames.append(pm.toImage())
        return frames
    except Exception:
        return []


def _pil_frames(im: Image.Image, limit: int) -> List[QImage]:
    frames: List[QImage] = []
    try:
        n = min(getattr(im, "n_frames", 1), limit)
        for i in range(n):
            try:
                im.seek(i)
                f = ImageOps.exif_transpose(im.copy())
                if f.mode not in ("RGB", "RGBA"):
                    f = f.convert("RGBA")
                frames.append(qimage_from_pil(f))
            except Exception:
                break
    except Exception:
        pass
    return frames


def load_image(path: str, max_frames: int = 120) -> LoadedImage:
    res = LoadedImage(path=path)
    try:
        st = os.stat(path)
        res.file_size = st.st_size
        res.mtime = st.st_mtime
    except OSError as e:
        res.error = f"无法读取文件：{e}"
        return res

    try:
        im = Image.open(path)
    except Exception as e:
        res.error = f"无法识别的图片格式：{e}"
        return res

    try:
        res.fmt = (im.format or "").upper()
        res.mode = im.mode
        res.exif = _exif_summary(im)
        try:
            res.exif_bytes = im.info.get("exif")
        except Exception:
            res.exif_bytes = None
        res.icc = im.info.get("icc_profile")

        im.load()
        base = ImageOps.exif_transpose(im)
        if base.mode not in ("RGB", "RGBA", "L"):
            base = base.convert("RGBA")
        elif base.mode == "L":
            base = base.convert("RGB")
        res.image = qimage_from_pil(base)

        n = getattr(im, "n_frames", 1) or 1
        if n > 1 and n <= max_frames:
            if res.fmt == "GIF":
                frames = _gif_frames(path, max_frames)
                res.frames = frames if frames else _pil_frames(im, max_frames)
            else:
                res.frames = _pil_frames(im, max_frames)
    except Exception as e:
        res.error = f"图片解析失败：{e}"
    return res


def load_qimage(path: str) -> Optional[QImage]:
    r = load_image(path, max_frames=1)
    return r.image


# ---------------------------------------------------------------- 缩略图

def make_thumbnail(path: str, box: int) -> Optional[QImage]:
    """快速缩略图：JPEG 走 draft 降采样，明显更快。"""
    try:
        im = Image.open(path)
        try:
            im.draft("RGB", (box * 2, box * 2))
        except Exception:
            pass
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        im.thumbnail((box, box), LANCZOS)
        return qimage_from_pil(im)
    except Exception:
        return None


# ---------------------------------------------------------------- 几何变换

def apply_transform(q: QImage, rot: int = 0, flip_h: bool = False,
                    flip_v: bool = False) -> QImage:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QTransform

    out = q
    if flip_h or flip_v:
        out = out.mirrored(flip_h, flip_v)
    rot = int(rot) % 360
    if rot:
        out = out.transformed(QTransform().rotate(rot), Qt.TransformationMode.SmoothTransformation)
    return out


def resize_qimage(q: QImage, width: int, height: int, smooth: bool = True) -> QImage:
    from PySide6.QtCore import Qt
    mode = Qt.TransformationMode.SmoothTransformation if smooth else Qt.TransformationMode.FastTransformation
    return q.scaled(max(1, int(width)), max(1, int(height)),
                    Qt.AspectRatioMode.IgnoreAspectRatio, mode)


def fit_dimensions(w: int, h: int, mode: str, val1: float, val2: float = 0,
                   keep_ratio: bool = True) -> Tuple[int, int]:
    """mode: 'percent' | 'width' | 'height' | 'long_edge' | 'exact' | 'box'"""
    w, h = max(1, int(w)), max(1, int(h))
    if mode == "percent":
        s = max(1.0, float(val1)) / 100.0
        return max(1, round(w * s)), max(1, round(h * s))
    if mode == "long_edge":
        edge = max(1.0, float(val1))
        s = edge / max(w, h)
        return max(1, round(w * s)), max(1, round(h * s))
    if mode == "width":
        nw = max(1.0, float(val1))
        s = nw / w
        return max(1, round(nw)), max(1, round(h * s))
    if mode == "height":
        nh = max(1.0, float(val1))
        s = nh / h
        return max(1, round(w * s)), max(1, round(nh))
    if mode == "box":
        bw, bh = max(1.0, float(val1)), max(1.0, float(val2))
        s = min(bw / w, bh / h)
        return max(1, round(w * s)), max(1, round(h * s))
    if mode == "exact":
        if keep_ratio:
            s = min(max(1.0, float(val1)) / w, max(1.0, float(val2)) / h)
            return max(1, round(w * s)), max(1, round(h * s))
        return max(1, int(val1)), max(1, int(val2))
    return w, h


# ---------------------------------------------------------------- 编码

def _flatten(im: Image.Image, color=(255, 255, 255)) -> Image.Image:
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, color + (255,))
        return Image.alpha_composite(bg, im).convert("RGB")
    return im.convert("RGB")


def _square_canvas(im: Image.Image) -> Image.Image:
    """ICO 需要正方形，居中放到透明画布上。"""
    im = im.convert("RGBA")
    side = max(im.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(im, ((side - im.width) // 2, (side - im.height) // 2), im)
    return canvas


def _fix_exif(exif_bytes: Optional[bytes], size: Tuple[int, int]) -> Optional[bytes]:
    if not exif_bytes:
        return None
    try:
        ex = Image.Exif()
        ex.load(exif_bytes)
        ex[274] = 1                      # 像素已按方向摆正
        ex[40962] = size[0]
        ex[40963] = size[1]
        return ex.tobytes()
    except Exception:
        return None


def encode_image(qimg: QImage, fmt_key: str, quality: int = 88,
                 keep_exif: bool = False, exif_bytes: Optional[bytes] = None,
                 icc: Optional[bytes] = None) -> bytes:
    spec = FORMAT_BY_KEY.get(fmt_key, FORMAT_BY_KEY["JPEG"])
    im = pil_from_qimage(qimg)

    if spec.key == "JPEG":
        im = _flatten(im)
        params = dict(format="JPEG", quality=int(quality), optimize=True,
                      progressive=int(quality) >= 85)
    elif spec.key == "PNG":
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        params = dict(format="PNG", optimize=True, compress_level=9)
    elif spec.key == "WEBP":
        params = dict(format="WEBP", quality=int(quality), method=4)
    elif spec.key == "BMP":
        im = _flatten(im)
        params = dict(format="BMP")
    elif spec.key == "TIFF":
        params = dict(format="TIFF", compression="tiff_lzw")
    elif spec.key == "GIF":
        im = _flatten(im).convert("P", palette=Image.Palette.ADAPTIVE, colors=256)
        params = dict(format="GIF", optimize=True)
    elif spec.key == "ICO":
        im = _square_canvas(im)
        side = im.width
        sizes = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256) if s <= side] or [(side, side)]
        params = dict(format="ICO", sizes=sizes)
    else:
        params = dict(format=spec.key)

    if keep_exif and spec.key in ("JPEG", "WEBP", "TIFF"):
        fixed = _fix_exif(exif_bytes, im.size)
        if fixed:
            params["exif"] = fixed
    if icc and spec.key in ("JPEG", "PNG", "WEBP", "TIFF"):
        params["icc_profile"] = icc

    buf = io.BytesIO()
    im.save(buf, **params)
    return buf.getvalue()


def estimate_size(qimg: QImage, fmt_key: str, quality: int = 88,
                  keep_exif: bool = False, exif_bytes: Optional[bytes] = None) -> int:
    try:
        return len(encode_image(qimg, fmt_key, quality, keep_exif, exif_bytes))
    except Exception:
        return 0


# ---------------------------------------------------------------- 压缩到目标体积

@dataclass
class CompressResult:
    data: bytes
    quality: int
    width: int
    height: int
    scale: float
    reached: bool
    fmt: str

    @property
    def size(self) -> int:
        return len(self.data)


def compress_to_target(qimg: QImage, fmt_key: str, target_bytes: int,
                       allow_resize: bool = True, keep_exif: bool = False,
                       exif_bytes: Optional[bytes] = None) -> CompressResult:
    """把图片编码到不超过 target_bytes：先降质量，必要时再缩尺寸。"""
    spec = FORMAT_BY_KEY.get(fmt_key, FORMAT_BY_KEY["JPEG"])
    if spec.key not in ("JPEG", "WEBP"):
        # 无损格式：不改质量，只能靠缩尺寸 / 调色板
        steps = [1.0] if not allow_resize else [1.0, .85, .7, .6, .5, .4, .32, .25, .18, .12]
        smallest: Optional[CompressResult] = None
        for s in steps:
            cur = qimg if s >= 1.0 else resize_qimage(qimg, qimg.width() * s, qimg.height() * s)
            if spec.key == "PNG" and s < 1.0:
                cur = cur.convertToFormat(QImage.Format.Format_RGBA8888)
            try:
                data = encode_image(cur, spec.key, 90, keep_exif, exif_bytes)
            except Exception:
                continue
            r = CompressResult(data, 90, cur.width(), cur.height(), s, len(data) <= target_bytes, spec.key)
            if r.reached:
                return r
            if smallest is None or r.size < smallest.size:
                smallest = r
        if smallest:
            return smallest
        data = encode_image(qimg, spec.key, 90)
        return CompressResult(data, 90, qimg.width(), qimg.height(), 1.0, False, spec.key)

    steps = [1.0] if not allow_resize else [1.0, .9, .8, .72, .64, .55, .46, .38, .3, .24, .18, .12]
    smallest: Optional[CompressResult] = None
    for s in steps:
        cur = qimg if s >= 1.0 else resize_qimage(qimg, max(1, int(qimg.width() * s)),
                                                  max(1, int(qimg.height() * s)))
        # 二分寻找"不超过目标体积"的最高质量
        lo, hi = 5, 95
        best: Optional[CompressResult] = None
        while lo <= hi:
            mid = (lo + hi) // 2
            try:
                data = encode_image(cur, spec.key, mid, keep_exif, exif_bytes)
            except Exception:
                break
            if len(data) <= target_bytes:
                best = CompressResult(data, mid, cur.width(), cur.height(), s, True, spec.key)
                lo = mid + 1
            else:
                hi = mid - 1
        if best is not None:
            return best
        # 记录最小可行样本，用于"尽力而为"
        try:
            data = encode_image(cur, spec.key, 5, keep_exif, exif_bytes)
            if smallest is None or len(data) < smallest.size:
                smallest = CompressResult(data, 5, cur.width(), cur.height(), s, False, spec.key)
        except Exception:
            pass
    if smallest is not None:
        return smallest
    data = encode_image(qimg, spec.key, 5)
    return CompressResult(data, 5, qimg.width(), qimg.height(), 1.0, False, spec.key)


# ---------------------------------------------------------------- 落盘

def write_bytes_atomic(path: str, data: bytes) -> None:
    folder = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".picsprite_", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        if os.path.exists(path):
            try:
                os.chmod(path, 0o666)
            except Exception:
                pass
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def save_qimage(qimg: QImage, path: str, fmt_key: str, quality: int = 88,
                keep_exif: bool = False, exif_bytes: Optional[bytes] = None,
                icc: Optional[bytes] = None) -> int:
    data = encode_image(qimg, fmt_key, quality, keep_exif, exif_bytes, icc)
    write_bytes_atomic(path, data)
    return len(data)


def save_with_options(qimg: QImage, path: str, fmt_key: str, quality: int = 88,
                      resize=None, target_bytes: int = 0, keep_exif: bool = False,
                      exif_bytes: Optional[bytes] = None,
                      icc: Optional[bytes] = None) -> Tuple[int, int, int, int]:
    """按"尺寸 + 体积 + 质量"组合保存，返回 (字节数, 宽, 高, 质量)。

    这是「另存为」和批量处理的统一出口，避免各处重复实现缩放逻辑。
    """
    img = qimg
    if resize:
        w, h = int(resize[0]), int(resize[1])
        if (w, h) != (qimg.width(), qimg.height()):
            img = resize_qimage(qimg, w, h)
    if target_bytes and target_bytes > 0:
        r = compress_to_target(img, fmt_key, target_bytes, True, keep_exif, exif_bytes)
        write_bytes_atomic(path, r.data)
        return r.size, r.width, r.height, r.quality
    size = save_qimage(img, path, fmt_key, quality, keep_exif, exif_bytes, icc)
    return size, img.width(), img.height(), quality


def save_qimage_with_budget(qimg: QImage, path: str, fmt_key: str, quality: int = 88,
                            target_bytes: int = 0, allow_resize: bool = True,
                            keep_exif: bool = False, exif_bytes: Optional[bytes] = None,
                            icc: Optional[bytes] = None) -> Tuple[int, int, int, int]:
    """返回 (文件大小, 宽, 高, 质量)。target_bytes>0 时自动压缩。"""
    if target_bytes and target_bytes > 0:
        r = compress_to_target(qimg, fmt_key, target_bytes, allow_resize, keep_exif, exif_bytes)
        # 压缩结果可能被缩放，直接写压缩后的字节
        write_bytes_atomic(path, r.data)
        return r.size, r.width, r.height, r.quality
    size = save_qimage(qimg, path, fmt_key, quality, keep_exif, exif_bytes, icc)
    return size, qimg.width(), qimg.height(), quality
