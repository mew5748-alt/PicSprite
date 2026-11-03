# -*- coding: utf-8 -*-
"""通用小工具：排序、文件大小、回收站、壁纸、资源管理器定位。"""
from __future__ import annotations

import ctypes
import os
import re
import subprocess
import sys
from typing import List

# ---------------------------------------------------------------- 文本 / 排序

def natural_key(text: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(text))]


def human_size(num: float) -> str:
    num = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(num)} {unit}"
            return f"{num:.1f} {unit}" if num < 100 else f"{num:.0f} {unit}"
        num /= 1024.0
    return f"{num:.1f} GB"


def parse_size_text(text: str) -> int:
    """把 '500KB' / '2M' / '120000' 解析成字节数。"""
    t = str(text).strip().lower().replace(" ", "")
    m = re.match(r"^([\d.]+)\s*(b|kb?|mb?|gb?)?$", t)
    if not m:
        raise ValueError("无法识别的体积格式")
    val = float(m.group(1))
    unit = m.group(2) or "kb"
    mult = {"b": 1, "kb": 1024, "k": 1024, "mb": 1024 ** 2, "m": 1024 ** 2,
            "gb": 1024 ** 3, "g": 1024 ** 3}
    return max(1, int(val * mult.get(unit, 1024)))


def safe_filename(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", name).strip(" .")
    return name or "未命名"


def unique_path(path: str) -> str:
    """如果已存在，追加 (1)(2)..."""
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    i = 1
    while True:
        cand = f"{root} ({i}){ext}"
        if not os.path.exists(cand):
            return cand
        i += 1


# ---------------------------------------------------------------- Windows 集成

if sys.platform == "win32":
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_uint16),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    FO_DELETE = 3
    FOF_SILENT = 0x0004
    FOF_NOCONFIRMATION = 0x0010
    FOF_ALLOWUNDO = 0x0040
    FOF_NOERRORUI = 0x0400
    SPI_SETDESKWALLPAPER = 20
    SPIF_UPDATEINIFILE = 0x01
    SPIF_SENDCHANGE = 0x02


def recycle(path: str) -> bool:
    """把文件放进回收站（可还原），失败返回 False。"""
    if sys.platform != "win32":
        try:
            os.remove(path)
            return True
        except OSError:
            return False
    try:
        op = SHFILEOPSTRUCTW()
        op.hwnd = None
        op.wFunc = FO_DELETE
        op.pFrom = path + "\0\0"
        op.pTo = None
        op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
        res = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        return res == 0 and not op.fAnyOperationsAborted
    except Exception:
        return False


def set_wallpaper(path: str) -> bool:
    if sys.platform != "win32":
        return False
    try:
        res = ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER, 0, path, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)
        return bool(res)
    except Exception:
        return False


def reveal_in_explorer(path: str) -> None:
    path = os.path.abspath(path)
    if sys.platform == "win32":
        try:
            subprocess.Popen(["explorer", "/select,", path])
            return
        except Exception:
            pass
    open_folder(os.path.dirname(path))


def open_folder(path: str) -> None:
    path = os.path.abspath(path)
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def dir_size(path: str) -> int:
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    except OSError:
        pass
    return total


def split_paths(text: str) -> List[str]:
    return [p for p in re.split(r'[\r\n]+', text) if p.strip()]
