# -*- coding: utf-8 -*-
"""批量处理：重命名 / 转换格式 / 调整尺寸 / 压缩体积。"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from PIL import Image

from . import imageio
from .util import natural_key, safe_filename, unique_path


@dataclass
class BatchOptions:
    # 重命名
    do_rename: bool = False
    pattern: str = "{name}"
    start_index: int = 1
    padding: int = 3
    find_text: str = ""
    replace_text: str = ""
    case_mode: str = "keep"          # keep / lower / upper / title
    # 转换
    do_convert: bool = False
    fmt: str = "JPEG"
    quality: int = 88
    keep_exif: bool = False
    # 尺寸 / 体积
    do_resize: bool = False
    resize_mode: str = "long_edge"   # long_edge / width / height / percent / exact
    resize_val1: float = 1920
    resize_val2: float = 1080
    target_bytes: int = 0
    # 输出
    out_mode: str = "subfolder"      # subfolder / custom / overwrite
    out_dir: str = ""
    subfolder: str = "已处理"
    backup: bool = True


@dataclass
class PlanItem:
    src: str
    dst: str
    action: str = ""
    status: str = ""
    ok: bool = False
    message: str = ""
    new_size: int = 0


def _case(text: str, mode: str) -> str:
    if mode == "lower":
        return text.lower()
    if mode == "upper":
        return text.upper()
    if mode == "title":
        return text.title()
    return text


def _image_dims(path: str) -> Tuple[int, int]:
    try:
        with Image.open(path) as im:
            return im.size
    except Exception:
        return (0, 0)


def render_name(path: str, opts: BatchOptions, index: int) -> str:
    stem, ext = os.path.splitext(os.path.basename(path))
    if opts.find_text:
        stem = stem.replace(opts.find_text, opts.replace_text)
    stem = _case(stem, opts.case_mode)
    try:
        mtime = os.path.getmtime(path)
        import datetime
        dt = datetime.datetime.fromtimestamp(mtime)
    except OSError:
        import datetime
        dt = datetime.datetime.now()
    w = h = 0
    tokens = {
        "{name}": stem,
        "{n}": str(index),
        "{nn}": str(index).zfill(max(1, opts.padding)),
        "{date}": dt.strftime("%Y%m%d"),
        "{time}": dt.strftime("%H%M%S"),
        "{parent}": os.path.basename(os.path.dirname(os.path.abspath(path))),
    }
    if "{w}" in opts.pattern or "{h}" in opts.pattern:
        w, h = _image_dims(path)
        tokens["{w}"] = str(w)
        tokens["{h}"] = str(h)

    out = opts.pattern or "{name}"
    for k, v in tokens.items():
        out = out.replace(k, v)
    out = out.replace("{ext}", "")
    out = safe_filename(out)
    if not out:
        out = stem
    return out


def target_ext(opts: BatchOptions, src: str) -> str:
    if opts.do_convert:
        return imageio.FORMAT_BY_KEY.get(opts.fmt, imageio.FORMAT_BY_KEY["JPEG"]).ext
    return os.path.splitext(src)[1].lower()


def out_folder_for(src: str, opts: BatchOptions) -> str:
    folder = os.path.dirname(os.path.abspath(src))
    if opts.out_mode == "custom" and opts.out_dir:
        return opts.out_dir
    if opts.out_mode == "subfolder":
        return os.path.join(folder, opts.subfolder or "已处理")
    return folder


def build_plan(paths: List[str], opts: BatchOptions) -> List[PlanItem]:
    plan: List[PlanItem] = []
    used: Dict[str, str] = {}
    for i, src in enumerate(paths):
        idx = opts.start_index + i
        folder = out_folder_for(src, opts)
        ext = target_ext(opts, src)
        if opts.do_rename:
            base = render_name(src, opts, idx)
        else:
            base = os.path.splitext(os.path.basename(src))[0]
            if opts.find_text:
                base = _case(base.replace(opts.find_text, opts.replace_text), opts.case_mode)
        dst = os.path.join(folder, base + ext)

        acts = []
        if opts.do_rename:
            acts.append("重命名")
        if opts.do_convert:
            acts.append("转 " + imageio.format_label(opts.fmt))
        if opts.do_resize:
            acts.append("调整尺寸")
        if opts.target_bytes:
            acts.append("压缩")
        if not acts:
            acts.append("无操作")

        item = PlanItem(src=src, dst=dst, action=" / ".join(acts))
        low = os.path.normcase(dst)
        if low in used and os.path.normcase(used[low]) != os.path.normcase(src):
            item.status = "与前面的文件重名"
        elif os.path.normcase(dst) == os.path.normcase(src) and not (
                opts.do_convert or opts.do_resize or opts.target_bytes):
            item.status = "名称未变化"
        elif os.path.exists(dst) and os.path.normcase(dst) != os.path.normcase(src):
            item.status = "目标已存在，将自动改名"
        used[low] = src
        plan.append(item)
    return plan


def _convert_one(src: str, dst: str, opts: BatchOptions) -> Tuple[bool, str, int]:
    loaded = imageio.load_image(src, max_frames=1)
    if loaded.image is None:
        return False, loaded.error or "读取失败", 0
    q = loaded.image
    if opts.do_resize:
        nw, nh = imageio.fit_dimensions(q.width(), q.height(), opts.resize_mode,
                                        opts.resize_val1, opts.resize_val2)
        q = imageio.resize_qimage(q, nw, nh)
    if opts.do_convert:
        fmt = opts.fmt
    else:
        fmt = loaded.fmt if loaded.fmt in imageio.FORMAT_BY_KEY else "JPEG"
    try:
        size, _w, _h, _q = imageio.save_qimage_with_budget(
            q, dst, fmt, opts.quality, opts.target_bytes,
            True, opts.keep_exif, loaded.exif_bytes, loaded.icc)
    except Exception as e:
        return False, f"保存失败：{e}", 0
    if not os.path.exists(dst):
        return False, "写入失败", 0
    return True, "", size


def execute_batch(paths: List[str], opts: BatchOptions,
                  progress: Optional[Callable[[int, int, str], None]] = None,
                  should_cancel: Optional[Callable[[], bool]] = None,
                  on_item: Optional[Callable[[PlanItem], None]] = None) -> Dict[str, object]:
    plan = build_plan(paths, opts)
    total = len(plan)
    done = 0
    failed: List[str] = []
    results: List[PlanItem] = []

    for i, item in enumerate(plan):
        if should_cancel and should_cancel():
            break
        if progress:
            progress(i, total, os.path.basename(item.src))
        src, dst = item.src, item.dst

        try:
            if item.status.startswith("与前面"):
                item.ok = False
                item.message = "重名，已跳过"
                failed.append(f"{os.path.basename(src)}：重名跳过")
                results.append(item)
                if on_item:
                    on_item(item)
                continue

            pure_rename = (not opts.do_convert and not opts.do_resize
                           and not opts.target_bytes)
            if pure_rename:
                if os.path.normcase(src) == os.path.normcase(dst):
                    item.ok = True
                    item.status = "无需处理"
                else:
                    if os.path.exists(dst):
                        dst = unique_path(dst)
                        item.dst = dst
                    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
                    os.rename(src, dst)
                    item.ok = True
                    item.status = "已重命名"
                    item.new_size = os.path.getsize(dst) if os.path.exists(dst) else 0
                results.append(item)
                if on_item:
                    on_item(item)
                done += 1
                continue

            # 需要真正处理像素
            if os.path.exists(dst) and os.path.normcase(dst) != os.path.normcase(src):
                dst = unique_path(dst)
                item.dst = dst
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)

            if opts.backup and os.path.exists(src):
                try:
                    bdir = os.path.join(os.path.dirname(os.path.abspath(src)), ".picsprite_backup")
                    os.makedirs(bdir, exist_ok=True)
                    shutil.copy2(src, os.path.join(bdir, os.path.basename(src)))
                except Exception:
                    pass

            ok, msg, size = _convert_one(src, dst, opts)
            item.ok = ok
            item.new_size = size
            item.status = "完成" if ok else "失败"
            if not ok:
                item.message = msg
                failed.append(f"{os.path.basename(src)}：{msg}")
            # 覆盖模式下换了文件名/扩展名，删除原文件
            if ok and opts.out_mode == "overwrite" and os.path.normcase(dst) != os.path.normcase(src):
                try:
                    os.remove(src)
                except OSError:
                    pass
        except Exception as e:                      # noqa: BLE001
            item.ok = False
            item.message = str(e)
            failed.append(f"{os.path.basename(src)}：{e}")

        results.append(item)
        if on_item:
            on_item(item)
        done += 1

    if progress:
        progress(total, total, "")
    return {"total": total, "done": done, "failed": failed, "items": results,
            "cancelled": bool(should_cancel and should_cancel())}


def sort_files(paths: List[str], mode: str) -> List[str]:
    if mode == "name_desc":
        return sorted(paths, key=lambda p: natural_key(os.path.basename(p)), reverse=True)
    if mode == "date_asc":
        return sorted(paths, key=lambda p: os.path.getmtime(p))
    if mode == "date_desc":
        return sorted(paths, key=lambda p: os.path.getmtime(p), reverse=True)
    if mode == "size_asc":
        return sorted(paths, key=lambda p: os.path.getsize(p))
    if mode == "size_desc":
        return sorted(paths, key=lambda p: os.path.getsize(p), reverse=True)
    return sorted(paths, key=lambda p: natural_key(os.path.basename(p)))
