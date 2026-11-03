# -*- coding: utf-8 -*-
"""后台任务：缩略图、图片载入、批量处理、体积预估。"""
from __future__ import annotations

import os
import traceback
from typing import List, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
from PySide6.QtGui import QImage

from . import imageio
from .batch import BatchOptions, execute_batch
from .thumbcache import ThumbCache


class Signals(QObject):
    result = Signal(object)
    error = Signal(str)
    progress = Signal(int, int, str)
    finished = Signal(object)


class ThumbTask(QRunnable):
    def __init__(self, path: str, box: int, cache: ThumbCache, generation: int) -> None:
        super().__init__()
        self.path = path
        self.box = box
        self.cache = cache
        self.generation = generation
        self.signals = Signals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            q = self.cache.get(self.path, self.box)
            if q is None:
                q = imageio.make_thumbnail(self.path, self.box)
                if q is not None:
                    self.cache.put(self.path, self.box, q)
            self.signals.result.emit((self.path, q, self.generation))
        except Exception:
            self.signals.result.emit((self.path, None, self.generation))


class LoadTask(QRunnable):
    def __init__(self, path: str, generation: int) -> None:
        super().__init__()
        self.path = path
        self.generation = generation
        self.signals = Signals()

    def run(self) -> None:
        try:
            loaded = imageio.load_image(self.path)
            self.signals.result.emit((self.generation, loaded))
        except Exception as e:                        # noqa: BLE001
            self.signals.error.emit(f"{e}")


class BatchTask(QRunnable):
    def __init__(self, paths: List[str], opts: BatchOptions, task_signals: Signals) -> None:
        super().__init__()
        self.paths = paths
        self.opts = opts
        self.signals = task_signals
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            summary = execute_batch(
                self.paths, self.opts,
                progress=lambda i, t, n: self.signals.progress.emit(i, t, n),
                should_cancel=lambda: self._cancel,
            )
            self.signals.finished.emit(summary)
        except Exception as e:                        # noqa: BLE001
            traceback.print_exc()
            self.signals.error.emit(str(e))


class EncodeTask(QRunnable):
    """预估编码后的体积（另存为对话框用）。"""

    def __init__(self, qimg: QImage, fmt: str, quality: int,
                 keep_exif: bool, exif_bytes: Optional[bytes]) -> None:
        super().__init__()
        self.qimg = qimg
        self.fmt = fmt
        self.quality = quality
        self.keep_exif = keep_exif
        self.exif_bytes = exif_bytes
        self.signals = Signals()

    def run(self) -> None:
        try:
            n = imageio.estimate_size(self.qimg, self.fmt, self.quality,
                                      self.keep_exif, self.exif_bytes)
            self.signals.result.emit(n)
        except Exception:
            traceback.print_exc()
            try:
                self.signals.result.emit(0)
            except Exception:
                pass


class TaskPool:
    """统一持有 QThreadPool，避免任务对象被提前回收。"""

    def __init__(self, max_threads: int = 4) -> None:
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(max(1, max_threads))
        self._keep = []

    def start(self, task: QRunnable) -> None:
        task.setAutoDelete(False)      # 生命周期交给 Python，避免信号对象被提前销毁
        self.pool.start(task)
        self._keep.append(task)
        if len(self._keep) > 200:
            self._keep = self._keep[-100:]

    def wait(self, ms: int = 2000) -> None:
        self.pool.waitForDone(ms)
