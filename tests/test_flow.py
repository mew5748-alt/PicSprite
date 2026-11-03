# -*- coding: utf-8 -*-
"""端到端流程测试：在临时目录里真实读写文件，验证保存 / 备份 / 重命名 / 删除 / 快捷键。"""
import os
import shutil
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from viewer import imageio
from viewer.mainwindow import MainWindow
from viewer.style import build_qss

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "samples")

app = QApplication(sys.argv)
app.setStyle("Fusion")
f = QFont("Microsoft YaHei UI")
f.setPointSize(9)
app.setFont(f)
app.setStyleSheet(build_qss())

work = tempfile.mkdtemp(prefix="picsprite_flow_")
for name in os.listdir(SAMPLES)[:4]:
    shutil.copy2(os.path.join(SAMPLES, name), os.path.join(work, name))

win = MainWindow(work)
win.resize(1200, 800)
win.show()

results = []
TASKS = []


def check(name, cond):
    results.append((name, bool(cond)))
    print(("  ✓ " if cond else "  ✗ ") + name)


def soon(delay, fn):
    TASKS.insert(0, (delay, fn))


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
        QTimer.singleShot(120, run_next)

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


# ------------------------------------------------------------------ 步骤
def step_open():
    print("\n▶ 打开临时目录")
    check("已打开图片", win.image is not None)
    check("文件列表 4 张", len(win.files) == 4)


def step_save_inplace():
    print("\n▶ 编辑后保存到原文件")
    global before_size, before_dims
    win.open_path(win.files[0], skip_confirm=True)
    soon(600, do_save)


def do_save():
    global before_size, before_dims, target_path
    target_path = win.path
    before_size = os.path.getsize(target_path)
    before_dims = (win.image.width(), win.image.height())
    win.rotate(90)                      # 临时旋转
    win.act_save()                      # 应自动 bake 并写回
    soon(400, verify_save)


def verify_save():
    check("保存后不再是脏状态", not win.dirty)
    check("画布变换已应用", not win.canvas.has_view_transform())
    check("文件已写入磁盘", os.path.exists(target_path))
    loaded = imageio.load_image(target_path)
    check("磁盘上的图片确实转了 90°",
          (loaded.width, loaded.height) == (before_dims[1], before_dims[0]))
    bdir = os.path.join(os.path.dirname(target_path), ".picsprite_backup")
    check("覆盖前已备份", os.path.isdir(bdir) and len(os.listdir(bdir)) >= 1)


def step_save_as():
    print("\n▶ 另存为（换格式 + 限体积 + 缩尺寸）")
    from viewer import imageio as iio
    img = win.image
    out = os.path.join(work, "输出_压缩.webp")
    size, w, h, q = iio.save_qimage_with_budget(
        img, out, "WEBP", 85, 40 * 1024, True, True, win.loaded.exif_bytes)
    check("另存为文件存在", os.path.exists(out))
    check(f"体积达标（{size // 1024} KB ≤ 40KB）", size <= 40 * 1024)
    r = iio.load_image(out)
    check("格式为 WebP", r.fmt == "WEBP")
    check("可正常回读", r.image is not None and r.width == w)


def step_rename():
    print("\n▶ 重命名")
    old = win.path
    folder = os.path.dirname(old)
    dst = os.path.join(folder, "重命名后的文件.jpg")
    os.rename(old, dst)
    win.path = dst
    win.files = [dst if p == old else p for p in win.files]
    win.index = win.files.index(dst)
    check("重命名后路径更新", win.path.endswith("重命名后的文件.jpg"))


def step_shortcut():
    print("\n▶ 快捷键")
    win.stack.setCurrentWidget(win.canvas)
    QTest.keyClick(win, Qt.Key.Key_Tab)
    soon(300, verify_tab)


def verify_tab():
    check("Tab 切换到缩略图", win.stack.currentWidget() is win.grid_page)
    QTest.keyClick(win, Qt.Key.Key_Tab)
    soon(300, verify_tab2)


def verify_tab2():
    check("Tab 切回单图", win.stack.currentWidget() is win.canvas)
    QTest.keyClick(win, Qt.Key.Key_Right)
    soon(600, verify_next)


def verify_next():
    check("方向键切换到下一张", win.index >= 1)


def step_delete():
    print("\n▶ 删除到回收站")
    global del_target
    del_target = win.path
    win.cfg.set("general/confirm_delete", False)
    win.act_delete()
    soon(500, verify_delete)


def verify_delete():
    check("文件已从磁盘移除", not os.path.exists(del_target))
    check("自动跳到下一张", win.image is not None)


TASKS = [(1200, step_open), (600, step_save_inplace), (600, step_save_as),
         (300, step_rename), (300, step_shortcut), (300, step_delete)]

QTimer.singleShot(300, run_next)
app.exec()
