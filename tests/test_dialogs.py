# -*- coding: utf-8 -*-
"""对话框级联测试：批量转换 / 批量重命名 / 压缩到指定大小 / 另存为参数收集。"""
import os
import shutil
import sys
import tempfile
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from viewer import imageio
from viewer.batchdialog import BatchDialog
from viewer.dialogs import CompressDialog, SaveAsDialog
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

work = tempfile.mkdtemp(prefix="picsprite_dlg_")
files = []
for name in os.listdir(SAMPLES)[:5]:
    dst = os.path.join(work, name)
    shutil.copy2(os.path.join(SAMPLES, name), dst)
    files.append(dst)
files.sort()

win = MainWindow(work)
win.resize(1100, 760)
win.show()

results = []
TASKS = []


def check(name, cond):
    results.append((name, bool(cond)))
    print(("  ✓ " if cond else "  ✗ ") + name)


def soon(delay, fn):
    TASKS.insert(0, (delay, fn))


def close_modals():
    """自动关掉弹出的提示框，避免测试卡住。"""
    for w in app.topLevelWidgets():
        if isinstance(w, QMessageBox) and w.isVisible():
            btn = w.button(QMessageBox.StandardButton.Yes)
            if btn is not None:
                btn.click()
            else:
                w.accept()
    QTimer.singleShot(200, close_modals)


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
        QTimer.singleShot(150, run_next)

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


# ------------------------------------------------------------------ 批量转换
def step_batch_convert():
    print("\n▶ 批量转换格式（→ PNG，输出到子文件夹）")
    global dlg
    dlg = BatchDialog(files, win)
    dlg.show()
    dlg.rename_check.setChecked(False)
    dlg.convert_check.setChecked(True)
    idx = dlg.fmt_box.findData("PNG")
    dlg.fmt_box.setCurrentIndex(idx)
    dlg.radio_sub.setChecked(True)
    dlg.sub_name.setText("转换输出")
    soon(500, lambda: check(f"预览操作列含转换（{dlg.table.item(0, 2).text()}）",
                            "PNG" in dlg.table.item(0, 2).text()))
    soon(400, lambda: dlg._start())


def check_batch_done():
    out = os.path.join(work, "转换输出")
    check("输出子文件夹已创建", os.path.isdir(out))
    names = sorted(os.listdir(out)) if os.path.isdir(out) else []
    check(f"输出文件数量（{len(names)}）", len(names) == len(files))
    if names:
        p = os.path.join(out, names[0])
        check("输出为 PNG", imageio.load_image(p).fmt == "PNG")
    ok_all = all(n.lower().endswith(".png") for n in names)
    check("扩展名全部为 .png", ok_all)


# ------------------------------------------------------------------ 批量重命名
def step_batch_rename():
    print("\n▶ 批量重命名（→ 假期_01…，原地覆盖）")
    global dlg2
    dlg2 = BatchDialog(files, win)
    dlg2.show()
    dlg2.rename_check.setChecked(True)
    dlg2.pattern.setText("假期_{nn}")
    dlg2.start_index.setValue(1)
    dlg2.padding.setValue(2)
    dlg2.convert_check.setChecked(False)
    dlg2.radio_over.setChecked(True)
    dlg2.backup_check.setChecked(True)
    dlg2._timer.stop()
    dlg2._refresh_preview()
    soon(400, lambda: check(f"重命名预览（{dlg2.table.item(0, 1).text()}）",
                            dlg2.table.item(0, 1).text().startswith("假期_01")))
    soon(300, lambda: dlg2._start())


def check_rename_done():
    names = sorted(os.listdir(work))
    renamed = [n for n in names if n.startswith("假期_")]
    check(f"重命名完成（{len(renamed)} 个）", len(renamed) == len(files))
    check("原文件已不存在", not any(os.path.basename(p) in names for p in files))


# ------------------------------------------------------------------ 压缩
def step_compress():
    print("\n▶ 压缩到指定大小")
    global cdlg
    target = next((p for p in glob_files() if p.lower().endswith(".jpg")), None)
    check("找到 JPG 用于压缩", target is not None)
    img = imageio.load_qimage(target)
    cdlg = CompressDialog(target, img, None, win)
    cdlg.show()
    cdlg.size_spin.setValue(30)
    soon(300, lambda: (check("压缩前体积 > 30KB", os.path.getsize(target) > 30 * 1024),
                       cdlg._run()))


def check_compress_done():
    out = cdlg.saved_path
    check("生成了压缩文件", bool(out) and os.path.exists(out))
    if out:
        size = os.path.getsize(out)
        check(f"压缩后 ≤ 30KB（{size // 1024} KB）", size <= 30 * 1024 + 512)
        check("压缩文件可回读", imageio.load_image(out).image is not None)


def glob_files():
    out = []
    for n in os.listdir(work):
        p = os.path.join(work, n)
        if os.path.isfile(p) and imageio.is_image_file(n):
            out.append(p)
    return sorted(out)


# ------------------------------------------------------------------ 另存为参数
def step_saveas_params():
    print("\n▶ 另存为参数收集")
    src = glob_files()[0]
    img = imageio.load_qimage(src)
    d = SaveAsDialog(src, img, None, None, "JPEG", win)
    idx = d.fmt_box.findData("WEBP")
    d.fmt_box.setCurrentIndex(idx)
    check("切换格式同步扩展名", d.path_edit.text().lower().endswith(".webp"))
    d.resize_check.setChecked(True)
    d.size_mode.setCurrentIndex(1)       # 限制长边
    d.val1.setValue(800)
    d.budget_check.setChecked(True)
    d.budget_spin.setValue(80)
    d.path_edit.setText(os.path.join(work, "参数测试.webp"))
    d.accept()
    p = d.params
    check("参数：格式 WebP", p.get("fmt") == "WEBP")
    check("参数：限制长边 800", p.get("resize") and max(p["resize"]) == 800)
    check("参数：目标 80KB", p.get("target_bytes") == 80 * 1024)
    # 真正按这些参数保存一次
    size, w, h, q = imageio.save_with_options(
        img, p["path"], p["fmt"], p["quality"], p["resize"], p["target_bytes"], False)
    check(f"按参数保存成功（{w}×{h}, {size // 1024}KB）",
          os.path.exists(p["path"]) and max(w, h) == 800 and size <= 80 * 1024)


TASKS = [(1200, step_batch_convert), (400, lambda: None), (2600, check_batch_done),
         (300, step_batch_rename), (2600, check_rename_done),
         (300, step_compress), (2200, check_compress_done),
         (300, step_saveas_params)]

QTimer.singleShot(250, close_modals)
QTimer.singleShot(400, run_next)
app.exec()
