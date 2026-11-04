# -*- coding: utf-8 -*-
"""看图精灵 安装程序。

单独打包成一个 exe，内部携带应用全部文件（payload.zip）。
支持：
    看图精灵-Setup.exe              图形安装向导
    看图精灵-Setup.exe /S           静默安装（默认目录 + 开始菜单快捷方式）
    看图精灵-Setup.exe /uninstall   图形卸载（安装目录下的 uninstall.exe 是它自己的副本）
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile

APP_NAME = "看图精灵"
APP_ID = "PicSprite"
APP_VERSION = "1.0.0"
APP_PUBLISHER = "PicSprite"
APP_EXE = APP_NAME + ".exe"
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

IMAGE_EXTS = [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff", ".ico"]


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
def resource(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def default_dir() -> str:
    return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                        "Programs", APP_ID)


def desktop_dir() -> str:
    """桌面目录（可能被用户重定向到 D 盘等，优先读注册表）。"""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders")
        val, _ = winreg.QueryValueEx(key, "Desktop")
        winreg.CloseKey(key)
        path = os.path.expandvars(val)
        if path and os.path.isdir(path):
            return path
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Desktop")


def startmenu_dir() -> str:
    base = os.environ.get("APPDATA", "")
    return os.path.join(base, "Microsoft", "Windows", "Start Menu", "Programs")


def hidden_popen(cmd: list) -> None:
    subprocess.Popen(cmd, creationflags=CREATE_NO_WINDOW,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def make_shortcut(lnk_path: str, target: str, workdir: str, icon: str,
                  desc: str = "") -> bool:
    """用 PowerShell 的 WScript.Shell 建快捷方式（免第三方依赖）。"""
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
        "$s.TargetPath='{tgt}';$s.WorkingDirectory='{wd}';$s.IconLocation='{ico}';"
        "$s.Description='{desc}';$s.Save()"
    ).format(lnk=lnk_path.replace("'", "''"), tgt=target.replace("'", "''"),
             wd=workdir.replace("'", "''"), ico=icon.replace("'", "''"),
             desc=desc.replace("'", "''"))
    try:
        parent = os.path.dirname(lnk_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
                        "-WindowStyle", "Hidden", "-Command", ps],
                       creationflags=CREATE_NO_WINDOW, timeout=40,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return os.path.exists(lnk_path)
    except Exception:
        return False


def register(app_dir: str, assoc: bool = True) -> None:
    """写入卸载信息 + 图片“打开方式”注册项（都在 HKCU，不需要管理员权限）。"""
    import winreg

    exe = os.path.join(app_dir, APP_EXE)
    uninst = os.path.join(app_dir, "uninstall.exe")
    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                               r"Software\Microsoft\Windows\CurrentVersion\Uninstall" + "\\" + APP_ID)
        for name, val in (
            ("DisplayName", APP_NAME),
            ("DisplayVersion", APP_VERSION),
            ("Publisher", APP_PUBLISHER),
            ("DisplayIcon", exe),
            ("InstallLocation", app_dir),
            ("UninstallString", f'"{uninst}" /uninstall'),
            ("QuietUninstallString", f'"{uninst}" /uninstall /S'),
        ):
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, val)
        winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
        size = 0
        for root, _dirs, files in os.walk(app_dir):
            for f in files:
                try:
                    size += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, max(1, size // 1024))
        winreg.CloseKey(key)
    except Exception:
        pass

    if not assoc:
        return

    progid = APP_ID + ".Image"
    defs = {
        rf"Software\Classes\{progid}": [("", APP_NAME + " 图片")],
        rf"Software\Classes\{progid}\DefaultIcon": [("", exe + ",0")],
        rf"Software\Classes\{progid}\shell\open\command": [("", f'"{exe}" "%1"')],
        rf"Software\Applications\{APP_EXE}": [("FriendlyAppName", APP_NAME)],
        rf"Software\Applications\{APP_EXE}\shell\open\command": [("", f'"{exe}" "%1"')],
    }
    for path, values in defs.items():
        try:
            k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, path)
            for name, val in values:
                winreg.SetValueEx(k, name, 0, winreg.REG_SZ, val)
            winreg.CloseKey(k)
        except Exception:
            pass

    # 各扩展名加入“打开方式”候选，不抢占系统默认程序
    for ext in IMAGE_EXTS:
        try:
            k = winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                                 rf"Software\Classes\{ext}\OpenWithProgids")
            winreg.SetValueEx(k, progid, 0, winreg.REG_SZ, "")
            winreg.CloseKey(k)
        except Exception:
            pass
    try:
        k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{progid}\SupportedTypes")
        for ext in IMAGE_EXTS:
            winreg.SetValueEx(k, ext, 0, winreg.REG_SZ, "")
        winreg.CloseKey(k)
    except Exception:
        pass


def unregister(app_dir: str) -> None:
    import winreg

    def del_recursive(path: str) -> None:
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, winreg.KEY_ALL_ACCESS)
        except OSError:
            return
        while True:
            try:
                sub = winreg.EnumKey(k, 0)
            except OSError:
                break
            del_recursive(path + "\\" + sub)
        winreg.CloseKey(k)
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except OSError:
            pass

    del_recursive(r"Software\Microsoft\Windows\CurrentVersion\Uninstall" + "\\" + APP_ID)
    del_recursive(rf"Software\Classes\{APP_ID}.Image")
    del_recursive(rf"Software\Applications\{APP_EXE}")
    for ext in IMAGE_EXTS:
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                               rf"Software\Classes\{ext}\OpenWithProgids", 0,
                               winreg.KEY_ALL_ACCESS)
            winreg.DeleteValue(k, APP_ID + ".Image")
            winreg.CloseKey(k)
        except OSError:
            pass


def is_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {APP_EXE}", "/NH"],
                             capture_output=True, timeout=20, creationflags=CREATE_NO_WINDOW)
        blob = out.stdout
        return bool(blob) and (APP_EXE.encode("gbk", "ignore") in blob
                               or APP_EXE.encode("utf-8", "ignore") in blob)
    except Exception:
        return False


def kill_running() -> None:
    hidden_popen(["taskkill", "/F", "/IM", APP_EXE])
    import time
    time.sleep(0.7)


# --------------------------------------------------------------------------- #
# 安装 / 卸载
# --------------------------------------------------------------------------- #
def payload_entries() -> list:
    with zipfile.ZipFile(resource("payload.zip")) as z:
        return [(i.filename, i.file_size) for i in z.infolist() if not i.is_dir()]


def do_install(app_dir: str, progress=None) -> None:
    """解压 payload 到 app_dir；progress(done_bytes, total_bytes, name)。"""
    os.makedirs(app_dir, exist_ok=True)
    with zipfile.ZipFile(resource("payload.zip")) as z:
        infos = [i for i in z.infolist() if not i.is_dir()]
        total = sum(i.file_size for i in infos) or 1
        done = 0
        for info in infos:
            z.extract(info, app_dir)
            done += info.file_size
            if progress:
                progress(done, total, info.filename)
    try:
        shutil.copy2(sys.executable, os.path.join(app_dir, "uninstall.exe"))
    except Exception:
        pass


def create_shortcuts(app_dir: str, desk: bool, menu: bool) -> None:
    exe = os.path.join(app_dir, APP_EXE)
    if desk:
        make_shortcut(os.path.join(desktop_dir(), APP_NAME + ".lnk"), exe, app_dir, exe,
                      "看图精灵 - 轻快看图工具")
    if menu:
        folder = startmenu_dir()
        os.makedirs(folder, exist_ok=True)
        make_shortcut(os.path.join(folder, APP_NAME + ".lnk"), exe, app_dir, exe,
                      "看图精灵 - 轻快看图工具")
        make_shortcut(os.path.join(folder, "卸载看图精灵.lnk"),
                      os.path.join(app_dir, "uninstall.exe"), app_dir, exe,
                      "卸载看图精灵")


def remove_shortcuts() -> None:
    for p in (os.path.join(desktop_dir(), APP_NAME + ".lnk"),
              os.path.join(startmenu_dir(), APP_NAME + ".lnk"),
              os.path.join(startmenu_dir(), "卸载看图精灵.lnk")):
        try:
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            pass


def do_uninstall(app_dir: str) -> None:
    remove_shortcuts()
    unregister(app_dir)
    if os.path.isdir(app_dir):
        for entry in list(os.scandir(app_dir)):
            try:
                if entry.is_dir(follow_symlinks=False):
                    shutil.rmtree(entry.path, ignore_errors=True)
                else:
                    os.remove(entry.path)
            except OSError:
                pass
    _schedule_cleanup(app_dir)


def _schedule_cleanup(app_dir: str) -> None:
    """用批处理循环重试删除目录（卸载器自己还在运行，文件被占用）。

    cmd 按系统 ANSI 代码页读取批处理，所以用 mbcs 写盘，避免中文路径乱码。
    """
    import tempfile
    bat = os.path.join(tempfile.gettempdir(), f"picsprite_uninst_{os.getpid()}.bat")
    body = (
        "@echo off\r\n"
        "set /a n=0\r\n"
        ":retry\r\n"
        "ping -n 2 127.0.0.1 >nul\r\n"
        f'rmdir /s /q "{app_dir}" 2>nul\r\n'
        f'if not exist "{app_dir}" goto done\r\n'
        "set /a n+=1\r\n"
        "if %n% lss 20 goto retry\r\n"
        ":done\r\n"
        'del /f /q "%~f0" >nul 2>nul\r\n'
    )
    try:
        with open(bat, "w", encoding="mbcs", errors="replace") as f:
            f.write(body)
    except Exception:
        hidden_popen(["cmd", "/c", f'ping -n 4 127.0.0.1 >nul & rmdir /s /q "{app_dir}"'])
        return
    hidden_popen(["cmd", "/c", bat])


# --------------------------------------------------------------------------- #
# 图形界面（PySide6）
# --------------------------------------------------------------------------- #
ACCENT = "#2f6fed"

_QSS_TEMPLATE = """
QWidget#root { background: #ffffff; }
QFrame#head { background: #2f6fed; }
QLabel#title { color: #ffffff; font-size: 21px; font-weight: 700; }
QLabel#subtitle { color: #dbe7ff; font-size: 11px; }
QLabel#section { color: #111827; font-size: 12px; font-weight: 600; }
QLabel#hint { color: #6b7280; font-size: 11px; }
QLineEdit {
    border: 1px solid #d5dbe6; border-radius: 6px; padding: 6px 9px;
    background: #fbfcfe; color: #111827; font-size: 12px;
}
QLineEdit:focus { border-color: #2f6fed; background: #ffffff; }
QPushButton {
    border: 1px solid #d5dbe6; border-radius: 6px; padding: 6px 16px;
    background: #ffffff; color: #374151; font-size: 12px;
}
QPushButton:hover { background: #f3f6fd; border-color: #b9c6dd; }
QPushButton#primary {
    background: #2f6fed; border: 0; color: #ffffff; font-weight: 600; padding: 8px 26px;
}
QPushButton#primary:hover { background: #1e59d0; }
QPushButton#primary:disabled { background: #a9c0f5; }
QCheckBox { color: #1f2937; font-size: 12px; spacing: 7px; }
QCheckBox::indicator {
    width: 15px; height: 15px; border: 1px solid #c7d0de;
    border-radius: 3px; background: #ffffff;
}
QCheckBox::indicator:checked {
    background: #2f6fed; border-color: #2f6fed; image: url("__CHECK__");
}
QProgressBar {
    border: 0; background: #eef1f6; border-radius: 4px; height: 8px;
    text-align: center; color: transparent;
}
QProgressBar::chunk { background: #2f6fed; border-radius: 4px; }
QFrame#card { background: #f7f9fc; border: 1px solid #eaeef5; border-radius: 8px; }
QLabel#cardTitle { color: #111827; font-size: 12px; font-weight: 600; }
QLabel#cardItem { color: #5b6472; font-size: 11px; }
QFrame#footer { background: #f7f9fc; border-top: 1px solid #e8ecf3; }
"""


def _check_png() -> str:
    """画一个白色对勾给复选框用（QSS 不支持矢量对勾）。"""
    import tempfile
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QPainter, QPen, QPixmap

    path = os.path.join(tempfile.gettempdir(), "picsprite_setup_check.png")
    if not os.path.exists(path):
        pm = QPixmap(36, 36)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(QPen(QColor("#ffffff"), 4.6, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawLine(QPointF(8, 18), QPointF(15, 26))
        p.drawLine(QPointF(15, 26), QPointF(28, 9))
        p.end()
        pm.save(path, "PNG")
    return path.replace("\\", "/")


def build_qss() -> str:
    return _QSS_TEMPLATE.replace("__CHECK__", _check_png())


def _app_icon():
    from PySide6.QtGui import QIcon
    path = resource("app.ico")
    return QIcon(path) if os.path.exists(path) else QIcon()


def run_gui() -> int:
    from PySide6.QtCore import QThread, Qt, Signal
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import (QApplication, QCheckBox, QFileDialog, QFrame,
                                   QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                                   QProgressBar, QPushButton, QVBoxLayout, QWidget)

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Microsoft YaHei UI", 9))
    app.setStyleSheet(build_qss())

    win = QWidget()
    win.setObjectName("root")
    win.setWindowTitle(f"{APP_NAME} {APP_VERSION} 安装程序")
    win.setWindowIcon(_app_icon())
    win.setFixedSize(660, 480)

    root = QVBoxLayout(win)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    head = QFrame()
    head.setObjectName("head")
    head.setFixedHeight(96)
    hl = QVBoxLayout(head)
    hl.setContentsMargins(30, 18, 30, 14)
    hl.setSpacing(2)
    t = QLabel(f"   {APP_NAME}")
    t.setObjectName("title")
    st = QLabel(f"   版本 {APP_VERSION}   ·   轻快的 Windows 看图工具")
    st.setObjectName("subtitle")
    hl.addWidget(t)
    hl.addWidget(st)
    root.addWidget(head)

    body = QWidget()
    bl = QVBoxLayout(body)
    bl.setContentsMargins(30, 20, 30, 10)
    bl.setSpacing(9)

    sec1 = QLabel("安装位置")
    sec1.setObjectName("section")
    bl.addWidget(sec1)

    row = QHBoxLayout()
    row.setSpacing(8)
    path_edit = QLineEdit(default_dir())
    path_edit.setCursorPosition(0)
    browse = QPushButton("浏览…")
    row.addWidget(path_edit, 1)
    row.addWidget(browse)
    bl.addLayout(row)

    hint = QLabel("安装到当前用户目录，无需管理员权限。")
    hint.setObjectName("hint")
    bl.addWidget(hint)
    bl.addSpacing(6)

    sec2 = QLabel("安装选项")
    sec2.setObjectName("section")
    bl.addWidget(sec2)

    cb_desk = QCheckBox("创建桌面快捷方式")
    cb_menu = QCheckBox("添加到开始菜单")
    cb_assoc = QCheckBox("在“打开方式”中加入看图精灵（不修改默认打开程序）")
    for w in (cb_desk, cb_menu, cb_assoc):
        w.setChecked(True)
        bl.addWidget(w)

    bl.addSpacing(10)
    card = QFrame()
    card.setObjectName("card")
    cl = QVBoxLayout(card)
    cl.setContentsMargins(16, 12, 16, 13)
    cl.setSpacing(4)
    ct = QLabel("安装后即可使用")
    ct.setObjectName("cardTitle")
    cl.addWidget(ct)
    for line in ("看图：JPG / PNG / WebP / TIFF / BMP / GIF / ICO 等格式，缩略图墙与幻灯片",
                 "编辑：裁剪、涂鸦、加文字、旋转翻转、调整尺寸、压缩到指定体积",
                 "批量：批量重命名、批量转换格式、批量调整大小"):
        it = QLabel("· " + line)
        it.setObjectName("cardItem")
        cl.addWidget(it)
    bl.addWidget(card)
    bl.addStretch(1)

    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(0)
    bar.setVisible(False)
    bl.addWidget(bar)
    status = QLabel("")
    status.setObjectName("hint")
    status.setMinimumHeight(18)
    status.setVisible(False)
    bl.addWidget(status)
    root.addWidget(body, 1)

    footer = QFrame()
    footer.setObjectName("footer")
    footer.setFixedHeight(64)
    fl = QHBoxLayout(footer)
    fl.setContentsMargins(24, 12, 22, 12)
    fl.addStretch(1)
    cancel = QPushButton("取消")
    install = QPushButton("安装")
    install.setObjectName("primary")
    install.setDefault(True)
    fl.addWidget(cancel)
    fl.addWidget(install)
    root.addWidget(footer)

    state = {"busy": False}

    def browse_dir() -> None:
        d = QFileDialog.getExistingDirectory(win, "选择安装位置", path_edit.text())
        if d:
            path_edit.setText(os.path.join(d, APP_ID))
            path_edit.setCursorPosition(0)

    browse.clicked.connect(browse_dir)

    class Worker(QThread):
        progressed = Signal(int, str)
        finished_ok = Signal(str)
        failed = Signal(str)

        def __init__(self, target: str, desk: bool, menu: bool, assoc: bool):
            super().__init__()
            self.target, self.desk, self.menu, self.assoc = target, desk, menu, assoc

        def run(self) -> None:
            try:
                entries = payload_entries()
                total = sum(s for _n, s in entries) or 1

                def cb(done: int, tot: int, name: str) -> None:
                    self.progressed.emit(int(done * 100 / tot), name)

                do_install(self.target, cb)
                create_shortcuts(self.target, self.desk, self.menu)
                register(self.target, self.assoc)
                self.finished_ok.emit(self.target)
            except Exception as exc:  # noqa: BLE001
                self.failed.emit(str(exc))

    workers: list = []

    def start_install() -> None:
        target = os.path.abspath(path_edit.text().strip() or default_dir())
        try:
            os.makedirs(target, exist_ok=True)
            probe = os.path.join(target, ".wtest")
            with open(probe, "w"):
                pass
            os.remove(probe)
        except Exception:
            QMessageBox.critical(win, "无法写入",
                                 f"没有权限写入：\n{target}\n\n请换一个位置。")
            return
        if is_running():
            r = QMessageBox.question(win, "正在运行",
                                     "看图精灵正在运行，是否关闭后继续安装？")
            if r != QMessageBox.StandardButton.Yes:
                return
            kill_running()

        state["busy"] = True
        install.setEnabled(False)
        browse.setEnabled(False)
        path_edit.setEnabled(False)
        bar.setVisible(True)
        status.setVisible(True)
        status.setText("正在安装…")

        w = Worker(target, cb_desk.isChecked(), cb_menu.isChecked(), cb_assoc.isChecked())
        w.progressed.connect(lambda pct, name: (bar.setValue(pct),
                                                status.setText(f"正在安装… {pct}%  {name}")))
        w.finished_ok.connect(on_done)
        w.failed.connect(on_fail)
        workers.append(w)
        w.start()

    def on_fail(msg: str) -> None:
        state["busy"] = False
        install.setEnabled(True)
        browse.setEnabled(True)
        path_edit.setEnabled(True)
        status.setText("安装失败")
        QMessageBox.critical(win, "安装失败", msg)

    def on_done(target: str) -> None:
        state["busy"] = False
        bar.setValue(100)
        status.setText("安装完成！")
        for w in (cancel, install):
            w.deleteLater()
        launch = QCheckBox("立即运行看图精灵")
        launch.setChecked(True)
        done = QPushButton("完成")
        done.setObjectName("primary")
        done.setDefault(True)
        fl.addWidget(launch)
        fl.addSpacing(10)
        fl.addWidget(done)

        def finish() -> None:
            if launch.isChecked():
                try:
                    os.startfile(os.path.join(target, APP_EXE))
                except Exception:
                    pass
            win.close()

        done.clicked.connect(finish)

    install.clicked.connect(start_install)
    cancel.clicked.connect(win.close)

    win.show()
    return app.exec()


def run_uninstall_gui() -> int:
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication, QMessageBox

    app = QApplication.instance() or QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei UI", 9))
    app_dir = os.path.dirname(os.path.abspath(sys.executable))
    r = QMessageBox.question(
        None, "卸载 " + APP_NAME,
        f"确定要卸载 {APP_NAME} 吗？\n\n安装位置：\n{app_dir}\n\n"
        "你的个人设置（%APPDATA%\\PicSprite）会保留。")
    if r != QMessageBox.StandardButton.Yes:
        return 0
    try:
        do_uninstall(app_dir)
    except Exception as exc:  # noqa: BLE001
        QMessageBox.critical(None, "卸载失败", str(exc))
    else:
        QMessageBox.information(None, "卸载完成",
                                f"{APP_NAME} 已卸载。\n\n如果桌面/开始菜单还残留快捷方式，"
                                "刷新一下即可消失。")
    return 0


def main() -> int:
    # 兼容 /uninstall、--uninstall、-u、/S、--silent 等各种写法
    flags = {a.lstrip("-/").lower() for a in sys.argv[1:]}
    silent = bool({"s", "silent", "quiet", "q"} & flags)
    if {"uninstall", "u", "remove"} & flags:
        if silent:
            do_uninstall(os.path.dirname(os.path.abspath(sys.executable)))
            return 0
        return run_uninstall_gui()
    if silent:
        target = default_dir()
        do_install(target)
        create_shortcuts(target, False, True)
        register(target, False)
        return 0
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())
