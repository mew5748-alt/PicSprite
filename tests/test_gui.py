# -*- coding: utf-8 -*-
"""界面冒烟测试 + 截图。

注意：这里全部用 QTimer 链式推进，不能用 QTest.qWait —— qWait 会占住 GIL，
后台线程（缩略图 / 编码预估）在等待期间无法执行，会得到假失败。
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from viewer import icons
from viewer.batchdialog import BatchDialog
from viewer.config import ACTIONS
from viewer.dialogs import SaveAsDialog
from viewer.mainwindow import MainWindow
from viewer.settingsdialog import SettingsDialog
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
app.setWindowIcon(icons.app_icon())

win = MainWindow(SAMPLES)
win.resize(1300, 850)
win.show()

results = []
TASKS = []


def check(name, cond):
    results.append((name, bool(cond)))
    print(("  ✓ " if cond else "  ✗ ") + name)


def shot(name, widget=None):
    (widget or win).grab().save(os.path.join(SHOTS, name))


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
    app.quit()


# ---------------------------------------------------------------- 步骤
def step_load():
    print("\n▶ 打开与显示")
    check("图片已加载", win.image is not None)
    check("打开的是第一张", win.path and "01" in os.path.basename(win.path))
    check("画布显示正常", win.canvas.has_image())
    check("信息面板已填充", "×" in win.info_values["尺寸"].text())
    check("状态栏尺寸", win.lbl_dims.text() == f"{win.image.width()} × {win.image.height()}")
    shot("01-viewer.png")


def step_transform():
    print("\n▶ 旋转 / 翻转 / 撤销")
    w0, h0 = win.image.width(), win.image.height()
    win.rotate(90)
    check("临时旋转生效", win.canvas.has_view_transform())
    win.canvas.bake_transform()
    check("旋转写入像素", (win.image.width(), win.image.height()) == (h0, w0))
    win.act_undo()
    check("撤销恢复原尺寸", (win.image.width(), win.image.height()) == (w0, h0))


def step_crop():
    print("\n▶ 裁剪")
    win.canvas.begin_crop(None)
    soon(300, finish_crop)


def finish_crop():
    shot("02-crop-mode.png")
    win.canvas._crop = QRectF(120, 80, 800, 560)
    ok = win.canvas.apply_crop()
    check("裁剪成功", ok and win.image.width() == 800 and win.image.height() == 560)
    check("裁剪后信息面板同步", "800" in win.info_values["尺寸"].text())


def step_draw():
    print("\n▶ 涂鸦 / 文字")
    win.canvas.begin_draw()
    cv = win.canvas
    QTest.mousePress(cv, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(200, 200))
    for i in range(1, 14):
        QTest.mouseMove(cv, QPoint(200 + i * 22, 200 + int(50 * (i % 4))))
    QTest.mouseRelease(cv, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                       QPoint(510, 240))
    check("涂鸦写入撤销栈", len(win.undo) >= 1)

    f = QFont("Microsoft YaHei")
    f.setPointSize(44)
    win.canvas.begin_text("看图精灵", f, QColor("#ffffff"), True)
    ok = win.canvas.commit_text()
    check("文字已合成", ok)


def step_edited_shot():
    shot("03-edited.png")


def step_grid():
    print("\n▶ 缩略图墙")
    win.toggle_grid()
    check("切换到缩略图", win.stack.currentWidget() is win.grid_page)
    soon(1500, check_grid)


def check_grid():
    g = win.grid_page.grid
    loaded = sum(1 for i in range(g.count())
                 if g.item(i).data(Qt.ItemDataRole.UserRole + 1) == "done")
    check("缩略图数量正确", g.count() == len(win.files))
    check(f"缩略图异步加载（{loaded}/{g.count()}）", loaded >= len(win.files) - 1)
    shot("04-grid.png")
    win.toggle_grid()
    check("切回单图", win.stack.currentWidget() is win.canvas)


def step_saveas():
    print("\n▶ 另存为对话框")
    win.open_path(win.files[0], skip_confirm=True)
    soon(600, open_saveas)


def open_saveas():
    d = SaveAsDialog(win.path, win.image, None, None, "JPEG", win)
    d.resize(600, 640)
    d.show()
    soon(1300, lambda: check_saveas(d))


def check_saveas(d):
    print("   预估:", d.estimate_label.text())
    check("另存为默认同目录", os.path.dirname(d.path_edit.text()) == win.folder)
    check("默认扩展名 jpg", d.path_edit.text().lower().endswith(".jpg"))
    check("体积预估已完成", "KB" in d.estimate_label.text() or "MB" in d.estimate_label.text())
    shot("05-saveas.png", d)
    d.quality.setValue(56)
    soon(900, lambda: check_saveas2(d))


def check_saveas2(d):
    print("   调整质量后:", d.estimate_label.text())
    check("质量联动预估更新", "计算中" not in d.estimate_label.text())
    d.close()


def step_batch():
    print("\n▶ 批量处理对话框")
    d = BatchDialog(win.files, win)
    d.resize(800, 740)
    d.show()
    soon(900, lambda: check_batch(d))


def check_batch(d):
    check("批量预览有数据", d.table.rowCount() == len(win.files))
    d.pattern.setText("旅行_{nn}")
    d.start_index.setValue(1)
    soon(600, lambda: check_batch_rename(d))


def check_batch_rename(d):
    new_name = d.table.item(0, 1).text()
    check(f"重命名预览生效（{new_name}）", new_name.startswith("旅行_001"))
    shot("06-batch.png", d)
    d.close()


def step_settings():
    print("\n▶ 设置对话框")
    d = SettingsDialog(win.cache, win)
    d.resize(660, 600)
    d.show()
    soon(500, lambda: check_settings(d))


def check_settings(d):
    check("快捷键条目完整", len(d._shortcut_editors) == len(win.actions))
    check("右键菜单可配置项", d.ctx_list.count() > 20)
    shot("07-settings.png", d)
    d.close()


def step_compress():
    print("\n▶ 压缩到指定大小")
    from viewer.imageio import compress_to_target
    r = compress_to_target(win.image, "JPEG", 60 * 1024, True)
    check(f"压缩达标（{r.size // 1024} KB / 目标 60KB）", r.size <= 60 * 1024 and r.reached)


def step_shortcuts():
    print("\n▶ 动作与右键菜单")
    missing = [a.id for a in ACTIONS if a.id not in win.actions]
    check("所有动作都已注册", not missing)
    menu = win._build_context_menu(None)
    check(f"右键菜单可构建（{len(menu.actions())} 项）", len(menu.actions()) > 10)
    menu.deleteLater()


TASKS = [(1500, step_load), (500, step_transform), (500, step_crop), (700, step_draw),
         (400, step_edited_shot), (400, step_grid), (900, step_saveas),
         (600, step_batch), (600, step_settings), (300, step_compress),
         (300, step_shortcuts)]

QTimer.singleShot(300, run_next)
app.exec()
