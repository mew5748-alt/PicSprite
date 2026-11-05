# -*- coding: utf-8 -*-
"""全局常量、动作注册表、配置读写。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, List

from PySide6.QtCore import QSettings

APP_NAME = "看图精灵"
APP_ID = "PicSprite"
ORGANIZATION = "PicSprite"
APP_VERSION = "1.2.0"

# ---------------------------------------------------------------- 路径

def app_data_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_ID)
    os.makedirs(d, exist_ok=True)
    return d


def cache_dir() -> str:
    d = os.path.join(app_data_dir(), "thumbcache")
    os.makedirs(d, exist_ok=True)
    return d


def backup_dir(folder: str) -> str:
    d = os.path.join(folder, ".picsprite_backup")
    os.makedirs(d, exist_ok=True)
    return d


# ---------------------------------------------------------------- 动作注册表

@dataclass
class ActionDef:
    id: str
    text: str
    shortcut: str = ""
    category: str = "文件"
    ctx: bool = True          # 是否可出现在右键菜单
    icon: str = ""
    tip: str = ""


CAT_FILE = "文件"
CAT_EDIT = "编辑"
CAT_VIEW = "视图"
CAT_IMAGE = "图片"
CAT_TOOL = "工具"
CAT_HELP = "帮助"

ACTIONS: List[ActionDef] = [
    # ---- 文件
    ActionDef("file.open", "打开图片…", "Ctrl+O", CAT_FILE, True, "open", "打开一张或多张图片"),
    ActionDef("file.open_folder", "打开文件夹…", "Ctrl+Shift+O", CAT_FILE, True, "folder", "浏览文件夹中的所有图片"),
    ActionDef("file.reload", "重新载入", "F5", CAT_FILE, True, "reload", "放弃修改并从磁盘重新读取"),
    ActionDef("file.save", "保存", "Ctrl+S", CAT_FILE, True, "save", "将当前编辑保存到原文件"),
    ActionDef("file.save_as", "另存为…", "Ctrl+Shift+S", CAT_FILE, True, "saveas", "转换格式 / 调整尺寸 / 控制体积"),
    ActionDef("file.compress", "压缩到指定大小…", "Ctrl+Alt+C", CAT_FILE, True, "compress", "压到指定 KB 大小"),
    ActionDef("file.print", "打印…", "Ctrl+P", CAT_FILE, True, "print", "打印当前图片 / 选中的图片，可导出 PDF"),
    ActionDef("file.print_preview", "打印预览…", "Ctrl+Shift+P", CAT_FILE, False, "print", "整页预览效果，可缩放翻页"),
    ActionDef("file.id_card", "身份证打印…", "Ctrl+Shift+I", CAT_FILE, True, "idcard", "自动裁出身份证正反面，按实际尺寸排到一张 A4 上"),
    ActionDef("file.rename", "重命名…", "F2", CAT_FILE, True, "rename", "重命名当前图片"),
    ActionDef("file.delete", "删除到回收站", "Del", CAT_FILE, True, "delete", "删除当前图片"),
    ActionDef("file.copy_image", "复制图片", "Ctrl+C", CAT_FILE, True, "copy", "把当前图片复制到剪贴板"),
    ActionDef("file.paste_image", "从剪贴板粘贴", "Ctrl+V", CAT_FILE, True, "paste", "把剪贴板中的图片作为新图片打开"),
    ActionDef("file.copy_path", "复制文件路径", "Ctrl+Alt+P", CAT_FILE, True, "path", ""),
    ActionDef("file.properties", "图片属性…", "Alt+Return", CAT_FILE, True, "info", ""),
    ActionDef("file.quit", "退出", "Ctrl+Q", CAT_FILE, False, "close", ""),

    # ---- 编辑
    ActionDef("edit.undo", "撤销", "Ctrl+Z", CAT_EDIT, True, "undo", ""),
    ActionDef("edit.redo", "重做", "Ctrl+Y", CAT_EDIT, True, "redo", ""),
    ActionDef("edit.crop", "裁剪", "C", CAT_EDIT, True, "crop", "拖动选区后按回车确认"),
    ActionDef("edit.draw", "涂鸦", "D", CAT_EDIT, True, "pen", "在图片上自由绘制"),
    ActionDef("edit.text", "添加文字", "T", CAT_EDIT, True, "text", "点击图片放置文字，可拖动定位"),
    ActionDef("edit.resize", "调整尺寸…", "Ctrl+Alt+R", CAT_EDIT, True, "resize", "修改图片像素尺寸"),
    ActionDef("edit.reset", "放弃所有修改", "", CAT_EDIT, True, "reload", "回到磁盘上的原始画面"),

    # ---- 视图
    ActionDef("view.grid", "缩略图浏览", "Tab", CAT_VIEW, True, "grid", "在单图与缩略图墙之间切换"),
    ActionDef("view.fullscreen", "全屏", "F11", CAT_VIEW, True, "fullscreen", ""),
    ActionDef("view.slideshow", "幻灯片播放", "F6", CAT_VIEW, True, "slideshow", "按间隔自动播放，Esc 退出"),
    ActionDef("view.zoom_in", "放大", "Ctrl+=", CAT_VIEW, True, "zoom_in", ""),
    ActionDef("view.zoom_out", "缩小", "Ctrl+-", CAT_VIEW, True, "zoom_out", ""),
    ActionDef("view.fit", "适应窗口", "Ctrl+0", CAT_VIEW, True, "fit", ""),
    ActionDef("view.actual", "实际大小 (100%)", "Ctrl+1", CAT_VIEW, True, "actual", ""),
    ActionDef("view.prev", "上一张", "Left", CAT_VIEW, True, "prev", ""),
    ActionDef("view.next", "下一张", "Right", CAT_VIEW, True, "next", ""),
    ActionDef("view.first", "第一张", "Home", CAT_VIEW, False, "", ""),
    ActionDef("view.last", "最后一张", "End", CAT_VIEW, False, "", ""),
    ActionDef("view.frame_prev", "上一帧", ",", CAT_VIEW, False, "prev", "多帧图片（GIF / TIFF）"),
    ActionDef("view.frame_next", "下一帧", ".", CAT_VIEW, False, "next", ""),
    ActionDef("view.animate", "播放/暂停动画", "Ctrl+Space", CAT_VIEW, False, "slideshow", ""),
    ActionDef("view.info", "信息面板", "F4", CAT_VIEW, False, "info", ""),
    ActionDef("view.bg", "切换画布背景", "B", CAT_VIEW, True, "bg", "深灰 / 中灰 / 浅色"),

    # ---- 图片（变换）
    ActionDef("image.rot_left", "向左旋转 90°", "Ctrl+L", CAT_IMAGE, True, "rotate_l", "临时旋转，保存后才会写入文件"),
    ActionDef("image.rot_right", "向右旋转 90°", "Ctrl+Shift+R", CAT_IMAGE, True, "rotate_r", ""),
    ActionDef("image.flip_h", "水平翻转", "Ctrl+H", CAT_IMAGE, True, "flip_h", ""),
    ActionDef("image.flip_v", "垂直翻转", "Ctrl+J", CAT_IMAGE, True, "flip_v", ""),
    ActionDef("image.rot_left_perm", "向左旋转并写入文件", "", CAT_IMAGE, True, "rotate_l", ""),
    ActionDef("image.rot_right_perm", "向右旋转并写入文件", "", CAT_IMAGE, True, "rotate_r", ""),
    ActionDef("image.flip_h_perm", "水平翻转并写入文件", "", CAT_IMAGE, True, "flip_h", ""),
    ActionDef("image.flip_v_perm", "垂直翻转并写入文件", "", CAT_IMAGE, True, "flip_v", ""),

    # ---- 工具
    ActionDef("tools.batch", "批量处理…", "Ctrl+B", CAT_TOOL, True, "batch", "批量重命名 / 转换格式 / 调整大小"),
    ActionDef("tools.settings", "设置…", "Ctrl+,", CAT_TOOL, False, "settings", ""),
    ActionDef("tools.clear_cache", "清空缩略图缓存", "", CAT_TOOL, False, "cache", ""),
    ActionDef("tools.open_cache", "打开缓存目录", "", CAT_TOOL, False, "folder", ""),
    ActionDef("tools.wallpaper", "设为桌面壁纸", "Ctrl+Alt+W", CAT_TOOL, True, "wallpaper", ""),
    ActionDef("tools.reveal", "在资源管理器中显示", "Ctrl+Shift+E", CAT_TOOL, True, "reveal", ""),

    # ---- 帮助
    ActionDef("help.shortcuts", "快捷键速查", "F1", CAT_HELP, True, "keyboard", ""),
    ActionDef("help.about", "关于看图精灵", "", CAT_HELP, True, "info", ""),
]

# 默认不出现在右键菜单里的动作（避免菜单过长；用户可在设置里自行打开）
_CTX_OFF = {
    "file.open_folder", "file.reload", "file.paste_image", "file.copy_path",
    "file.quit", "edit.resize", "edit.reset",
    "view.grid", "view.fullscreen", "view.slideshow", "view.zoom_in", "view.zoom_out",
    "view.fit", "view.actual", "view.prev", "view.next", "view.bg",
    "image.rot_left_perm", "image.rot_right_perm", "image.flip_h_perm", "image.flip_v_perm",
    "tools.clear_cache", "tools.open_cache", "help.shortcuts", "help.about",
}
for _a in ACTIONS:
    if _a.id in _CTX_OFF:
        _a.ctx = False

# 右键菜单默认顺序（按使用频率）
DEFAULT_CONTEXT = [
    "file.open", "file.save", "file.save_as", "file.compress", "file.print",
    "file.id_card",
    "edit.undo", "edit.redo", "edit.crop", "edit.draw", "edit.text",
    "image.rot_left", "image.rot_right", "image.flip_h", "image.flip_v",
    "file.rename", "file.delete", "file.copy_image", "file.copy_path",
    "tools.batch", "tools.wallpaper", "tools.reveal",
    "file.properties",
]

ACTION_MAP: Dict[str, ActionDef] = {a.id: a for a in ACTIONS}

# ---------------------------------------------------------------- 默认偏好

DEFAULTS = {
    "general/open_last": True,
    "general/last_folder": "",
    "general/thumb_size": 172,
    "general/sort": "name_asc",
    "general/slideshow_interval": 3,
    "general/loop": True,
    "general/confirm_delete": True,
    "general/backup_before_overwrite": True,
    "general/smooth_zoom": True,
    "general/preload_neighbors": True,
    "view/canvas_bg": "dark",
    "view/checkerboard": True,
    "cache/max_mb": 800,
    # 打印偏好
    "print/per_page": 1,
    "print/scale": "fit",
    "print/margin_mm": 6.0,
    "print/gap_mm": 4.0,
    "print/show_title": True,
    "print/show_date": False,
    "print/duplex": "none",
    "print/printer": "",
    # 身份证打印偏好
    "idcard/layout": "vertical",
    "idcard/gap_mm": 18,
    "idcard/margin_mm": 10,
    "idcard/border": False,
    "idcard/copies": 1,
    "recent/files": "[]",
    "recent/folders": "[]",
}


class Settings:
    """基于 ini 文件的配置（便携、可读、跨版本稳定）。"""

    def __init__(self) -> None:
        self.path = os.path.join(app_data_dir(), "settings.ini")
        self.q = QSettings(self.path, QSettings.Format.IniFormat)

    # -- 通用
    def get(self, key: str, default=None):
        if default is None:
            default = DEFAULTS.get(key, None)
        v = self.q.value(key, default)
        return v

    def set(self, key: str, value) -> None:
        self.q.setValue(key, value)
        self.q.sync()

    def get_bool(self, key: str, default: bool = False) -> bool:
        v = self.q.value(key, DEFAULTS.get(key, default))
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "on")
        return bool(v)

    def get_int(self, key: str, default: int = 0) -> int:
        try:
            return int(self.q.value(key, DEFAULTS.get(key, default)))
        except (TypeError, ValueError):
            return default

    # -- 快捷键
    def shortcut(self, action_id: str) -> str:
        d = ACTION_MAP[action_id].shortcut if action_id in ACTION_MAP else ""
        v = self.q.value("shortcut/" + action_id, d)
        return "" if v is None else str(v)

    def set_shortcut(self, action_id: str, seq: str) -> None:
        self.q.setValue("shortcut/" + action_id, seq)
        self.q.sync()

    def reset_shortcuts(self) -> None:
        for a in ACTIONS:
            self.q.remove("shortcut/" + a.id)
        self.q.sync()

    # -- 右键菜单
    def context_items(self) -> List[List]:
        raw = self.q.value("ui/context_menu", "")
        if not raw:
            items = [[aid, True] for aid in DEFAULT_CONTEXT if aid in ACTION_MAP]
            have = {i[0] for i in items}
            items += [[a.id, a.ctx] for a in ACTIONS if a.id not in have]
            return items
        try:
            items = json.loads(raw)
            known = set(ACTION_MAP)
            items = [[i[0], bool(i[1])] for i in items if i and i[0] in known]
            listed = {i[0] for i in items}
            for a in ACTIONS:            # 新版本新增的动作自动补上
                if a.ctx and a.id not in listed:
                    items.append([a.id, True])
            return items
        except Exception:
            items = [[aid, True] for aid in DEFAULT_CONTEXT if aid in ACTION_MAP]
            have = {i[0] for i in items}
            items += [[a.id, a.ctx] for a in ACTIONS if a.id not in have]
            return items

    def set_context_items(self, items: List[List]) -> None:
        self.q.setValue("ui/context_menu", json.dumps(items, ensure_ascii=False))
        self.q.sync()

    # -- 最近使用
    def recent(self, kind: str, limit: int = 12) -> List[str]:
        try:
            data = json.loads(self.q.value("recent/" + kind, "[]") or "[]")
            return [str(x) for x in data][:limit]
        except Exception:
            return []

    def push_recent(self, kind: str, path: str, limit: int = 12) -> None:
        if not path:
            return
        data = [p for p in self.recent(kind, 50) if os.path.normcase(p) != os.path.normcase(path)]
        data.insert(0, path)
        self.q.setValue("recent/" + kind, json.dumps(data[:limit], ensure_ascii=False))
        self.q.sync()


settings = Settings()
