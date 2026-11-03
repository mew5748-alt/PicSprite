# -*- coding: utf-8 -*-
"""缩略图磁盘缓存（按 路径+mtime+尺寸 做键，LRU 清理）。"""
from __future__ import annotations

import hashlib
import os
import threading
import time
from collections import OrderedDict
from typing import Optional

from PIL import Image
from PySide6.QtGui import QImage

from . import imageio
from .util import dir_size


class ThumbCache:
    def __init__(self, directory: str, max_bytes: int = 800 * 1024 * 1024) -> None:
        self.dir = directory
        os.makedirs(self.dir, exist_ok=True)
        self.max_bytes = int(max_bytes)
        self._mem: "OrderedDict[str, QImage]" = OrderedDict()
        self._mem_limit = 400
        self._lock = threading.Lock()
        self._pruned = False
        self._count = 0

    # ---------------------------------------------------------- 键
    @staticmethod
    def key(path: str, box: int) -> str:
        try:
            st = os.stat(path)
            raw = f"{os.path.normcase(os.path.abspath(path))}|{int(st.st_mtime)}|{st.st_size}|{box}"
        except OSError:
            raw = f"{path}|0|0|{box}"
        return hashlib.sha1(raw.encode("utf-8", "ignore")).hexdigest()

    def _file(self, key: str) -> str:
        return os.path.join(self.dir, key[:2], key + ".jpg")

    # ---------------------------------------------------------- 读写
    def get(self, path: str, box: int) -> Optional[QImage]:
        k = self.key(path, box)
        with self._lock:
            hit = self._mem.get(k)
            if hit is not None:
                self._mem.move_to_end(k)
                return hit
        f = self._file(k)
        if not os.path.exists(f):
            return None
        try:
            im = Image.open(f)
            im.load()
            q = imageio.qimage_from_pil(im.convert("RGB"))
        except Exception:
            try:
                os.remove(f)
            except OSError:
                pass
            return None
        self._remember(k, q)
        return q

    def put(self, path: str, box: int, qimg: QImage) -> None:
        k = self.key(path, box)
        self._remember(k, qimg)
        f = self._file(k)
        try:
            os.makedirs(os.path.dirname(f), exist_ok=True)
            im = imageio.pil_from_qimage(qimg)
            if im.mode != "RGB":
                bg = Image.new("RGB", im.size, (255, 255, 255))
                if im.mode == "RGBA":
                    bg.paste(im, mask=im.split()[-1])
                else:
                    bg.paste(im.convert("RGB"))
                im = bg
            tmp = f + ".tmp"
            im.save(tmp, "JPEG", quality=82, optimize=True)
            os.replace(tmp, f)
            self._count += 1
        except Exception:
            pass

    def _remember(self, k: str, q: QImage) -> None:
        with self._lock:
            self._mem[k] = q
            self._mem.move_to_end(k)
            while len(self._mem) > self._mem_limit:
                self._mem.popitem(last=False)

    def invalidate(self, path: str) -> None:
        """文件被修改后清掉它的所有尺寸缓存。"""
        base = os.path.normcase(os.path.abspath(path))
        with self._lock:
            for k in list(self._mem):
                pass
        # 磁盘上无法反查路径，靠 mtime 变化自然失效

    # ---------------------------------------------------------- 维护
    def size_bytes(self) -> int:
        return dir_size(self.dir)

    def count_files(self) -> int:
        n = 0
        for root, _d, files in os.walk(self.dir):
            n += len(files)
        return n

    def clear(self) -> None:
        with self._lock:
            self._mem.clear()
        for root, _dirs, files in os.walk(self.dir, topdown=False):
            for f in files:
                try:
                    os.remove(os.path.join(root, f))
                except OSError:
                    pass
            try:
                os.rmdir(root)
            except OSError:
                pass
        os.makedirs(self.dir, exist_ok=True)

    def prune_async(self) -> None:
        if self._pruned:
            return
        self._pruned = True
        threading.Thread(target=self.prune, daemon=True).start()

    def prune(self) -> int:
        """超过上限时按最久未访问删除，直到降到 70%。"""
        try:
            total = self.size_bytes()
        except Exception:
            return 0
        if total <= self.max_bytes:
            return 0
        entries = []
        for root, _dirs, files in os.walk(self.dir):
            for f in files:
                p = os.path.join(root, f)
                try:
                    st = os.stat(p)
                    entries.append((st.st_atime, st.st_size, p))
                except OSError:
                    pass
        entries.sort()
        target = int(self.max_bytes * 0.7)
        removed = 0
        for _atime, size, p in entries:
            if total <= target:
                break
            try:
                os.remove(p)
                total -= size
                removed += 1
            except OSError:
                pass
        return removed
