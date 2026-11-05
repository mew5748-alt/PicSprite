# -*- coding: utf-8 -*-
"""缩略图栏（左侧常驻缩略图）与"打开文件夹默认进缩略图墙"的行为测试。

与其它 GUI 测试一样用 QTimer 链式推进，不用 QTest.qWait（会占住 GIL）。
"""
import os
import shutil
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from viewer.mainwindow import MainWindow
from viewer.style import build_qss

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "samples")
SHOTS = os.path.join(HERE, "shots")
os.makedirs(SHOTS, exist_ok=True)

app = QApplication(sys.argv)
app.setStyle("Fusion")
f = QFont("Microsoft YaHei UI")
f.setPointSize(9)
app.setFont(f)
app.setStyleSheet(build_qss())

# 两个临时目录：A 有 4 张，B 有 3 张，另有空目录
work = tempfile.mkdtemp(prefix="picsprite_strip_")
names = sorted(n for n in os.listdir(SAMPLES) if os.path.isfile(os.path.join(SAMPLES, n)))
folder_a = os.path.join(work, "A")
folder_b = os.path.join(work, "B")
folder_empty = os.path.join(work, "空文件夹")
for d in (folder_a, folder_b, folder_empty):
    os.makedirs(d, exist_ok=True)
for n in names[:4]:
    shutil.copy2(os.path.join(SAMPLES, n), os.path.join(folder_a, n))
for n in names[4:7]:
    shutil.copy2(os.path.join(SAMPLES, n), os.path.join(folder_b, n))

win = MainWindow(folder_a)
win.resize(1300, 850)
win.show()

results = []
TASKS = []
_old_show_strip = win.cfg.get_bool("view/show_strip", True)


def check(name, cond):
    results.append((name, bool(cond)))
    print(("  ✓ " if cond else "  ✗ ") + name)


def run_next():
    if not TASKS:
        finish()
        return
    delay, fn = TASKS.pop(0)

    def go():
        try:
            fn()
        except Exception:
            traceback.print_exc()
            results.append((getattr(fn, "__name__", "step"), False))
        QTimer.singleShot(100, run_next)

    QTimer.singleShot(delay, go)


def finish():
    ok = sum(1 for _n, c in results if c)
    print(f"\n通过 {ok}/{len(results)} 项")
    if ok != len(results):
        print("失败项:", [n for n, c in results if not c])
    win.dirty = False
    win.close()
    shutil.rmtree(work, ignore_errors=True)
    app.quit()


strip = win.strip_panel.strip


# ---------------------------------------------------------------- 步骤
def step_initial():
    print("\n▶ 缩略图栏随文件夹出现")
    check("缩略图栏可见", win.strip_panel.isVisible())
    check("条目数 = 文件夹图片数", strip.count() == len(win.files) == 4)
    check("缩略图栏文件列表一致", strip.files() == win.files)
    check("当前图片已高亮", os.path.normcase(strip.current_path() or "")
          == os.path.normcase(win.path or ""))
    check("计数文字正确", win.strip_panel.count.text() == "4 张")
    win.grab().save(os.path.join(SHOTS, "10-strip.png"))


def check_thumbs():
    done = sum(1 for i in range(strip.count())
               if strip.item(i).data(Qt.ItemDataRole.UserRole + 1) == "done")
    real = sum(1 for i in range(strip.count()) if not strip.item(i).icon().isNull())
    check(f"缩略图异步加载（{done}/{strip.count()}）", done >= strip.count() - 1)
    check(f"图标已生成（{real}/{strip.count()}）", real >= strip.count() - 1)
    win.grab().save(os.path.join(SHOTS, "11-strip-loaded.png"))


def step_click():
    print("\n▶ 单击缩略图切换图片")
    global target
    item = strip.item(2)
    target = item.data(Qt.ItemDataRole.UserRole)
    rect = strip.visualItemRect(item)
    QTest.mouseClick(strip.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, rect.center())


def check_click():
    check("已切换到被点的图片", os.path.normcase(win.path or "") == os.path.normcase(target))
    check("视图为单图", win.stack.currentWidget() is win.canvas)
    check("画布有内容", win.canvas.has_image())
    check("高亮跟随", os.path.normcase(strip.current_path() or "") == os.path.normcase(target))


def step_folder_to_grid():
    print("\n▶ 打开文件夹默认进入缩略图墙")
    win.open_folder(folder_b)
    check("默认视图是缩略图墙", win.stack.currentWidget() is win.grid_page)
    check("整页网格已刷新", win.grid_page.grid.count() == 3)
    check("缩略图栏同步到新文件夹", strip.count() == 3 and len(strip.files()) == 3)
    win.grab().save(os.path.join(SHOTS, "12-folder-grid.png"))


def check_bg_load():
    check("后台已备好首图", win.image is not None and win.folder == os.path.abspath(folder_b))
    check("首图属于新文件夹", os.path.dirname(os.path.normcase(win.loaded.path))
          == os.path.normcase(os.path.abspath(folder_b)))
    check("网格中已选中首图", win.grid_page.current_path() is not None)


def step_click_from_grid():
    print("\n▶ 网格中单击缩略图栏也能直接看图")
    item = strip.item(1)
    global target2
    target2 = item.data(Qt.ItemDataRole.UserRole)
    QTest.mouseClick(strip.viewport(), Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, strip.visualItemRect(item).center())


def check_from_grid():
    check("已切回单图", win.stack.currentWidget() is win.canvas)
    check("打开的是所选图片", os.path.normcase(win.path or "") == os.path.normcase(target2))
    check("Tab 状态与视图一致", not win.actions["view.grid"].isChecked())


def step_toggle():
    print("\n▶ 显示 / 隐藏缩略图栏")
    win.toggle_strip()
    check("已隐藏", not win.strip_panel.isVisible())
    check("配置写入关闭", win.cfg.get_bool("view/show_strip") is False)
    win.toggle_strip()
    check("已重新显示", win.strip_panel.isVisible())
    check("配置写入开启", win.cfg.get_bool("view/show_strip") is True)
    check("动作可勾选且同步", win.actions["view.strip"].isCheckable()
          and win.actions["view.strip"].isChecked())


def step_size():
    print("\n▶ 缩略图尺寸")
    strip.set_thumb_size(140)
    check("缩略图放大到 140", strip.thumb_size() == 140
          and strip.iconSize() == QSize(140, 105))
    strip.set_thumb_size(104)
    check("缩略图恢复 104", strip.thumb_size() == 104)


def step_empty():
    print("\n▶ 空文件夹")
    win.open_folder(folder_empty, switch_grid=False)
    check("不会崩溃且列表为空", strip.files() == [])
    check("显示占位提示", strip.count() == 1)
    check("状态栏提示无图片", "没有" in win.info_name.text() or win.image is None)


def step_restore():
    print("\n▶ 恢复设置")
    win.cfg.set("view/show_strip", bool(_old_show_strip))
    check("设置已还原", str(win.cfg.get_bool("view/show_strip")).lower()
          == str(bool(_old_show_strip)).lower())


TASKS = [
    (300, step_initial),
    (1700, check_thumbs),
    (200, step_click),
    (1100, check_click),
    (300, step_folder_to_grid),
    (1400, check_bg_load),
    (200, step_click_from_grid),
    (1100, check_from_grid),
    (200, step_toggle),
    (200, step_size),
    (300, step_empty),
    (200, step_restore),
]
QTimer.singleShot(50, run_next)
app.exec()
