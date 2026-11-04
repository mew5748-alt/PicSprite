# -*- coding: utf-8 -*-
"""图形安装向导自动化测试：自动点「安装」，等进度跑完，验证产物后清理。

用法：python tests/test_setup_gui.py
依赖：先跑过一次 tools/build_release.py（需要 build/run-*/payload.zip）
"""
from __future__ import annotations

import glob
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "installer"))

os.environ.setdefault("QT_QPA_PLATFORM", "windows")

from PySide6.QtCore import QTimer                                  # noqa: E402
from PySide6.QtWidgets import QApplication, QCheckBox, QLabel, QPushButton  # noqa: E402

import setup_main as S                                             # noqa: E402

RESULTS: list = []


def check(name: str, ok: bool, extra: str = "") -> None:
    RESULTS.append((name, bool(ok)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{('  ' + extra) if extra else ''}",
          flush=True)


# ---------------------------------------------------------------- 环境准备
_cands = sorted(glob.glob(os.path.join(ROOT, "build", "run-*", "payload.zip")),
                key=os.path.getmtime)
if not _cands:
    print("找不到 payload.zip，请先运行 python tools/build_release.py")
    sys.exit(2)
PAYLOAD = _cands[-1]
print(f"payload: {PAYLOAD}  ({os.path.getsize(PAYLOAD) / 1024 / 1024:.1f} MB)", flush=True)

BASE = os.path.join(ROOT, "build", "tmp-gui-install")
TARGET = os.path.join(BASE, "PicSprite")


def _resource(name: str) -> str:
    """从源码运行时：payload 指向构建产物，图标从 assets 取。"""
    if name == "payload.zip":
        return PAYLOAD
    p = os.path.join(ROOT, "assets", name)
    if os.path.exists(p):
        return p
    return os.path.join(os.path.dirname(os.path.abspath(S.__file__)), name)


S.resource = _resource
S.default_dir = lambda: TARGET          # 装到构建目录，别碰真实安装
S.desktop_dir = lambda: os.path.join(BASE, "desk")
S.startmenu_dir = lambda: os.path.join(BASE, "menu")

if os.path.isdir(BASE):
    shutil.rmtree(BASE, ignore_errors=True)

# ---------------------------------------------------------------- 驱动逻辑
_orig_exec = QApplication.exec
_deadline = time.time() + 240
_state = {"clicked": False, "finished": False}


def _widgets():
    app = QApplication.instance()
    return [w for w in app.topLevelWidgets() if w.isVisible()]


def _find_primary():
    for w in _widgets():
        for b in w.findChildren(QPushButton):
            if b.objectName() == "primary" and b.isEnabled():
                return b
    return None


def _status_text() -> str:
    for w in _widgets():
        for lb in w.findChildren(QLabel):
            t = lb.text() or ""
            if lb.isVisible() and ("安装完成" in t or "安装失败" in t or "正在安装" in t):
                return t
    return ""


def _tick() -> None:
    app = QApplication.instance()
    if time.time() > _deadline:
        print("!! 超时", flush=True)
        for w in _widgets():
            w.close()
        app.exit(1)
        return

    st = _status_text()
    if not _state["clicked"]:
        btn = _find_primary()
        if btn is not None and btn.text() == "安装":
            btn.click()
            _state["clicked"] = True
            print("  已点击「安装」", flush=True)
        QTimer.singleShot(150, _tick)
        return

    if "安装完成" in st:
        _state["finished"] = True
        # 取消“立即运行”，再点完成关闭窗口
        for w in _widgets():
            for cb in w.findChildren(QCheckBox):
                if "运行" in cb.text():
                    cb.setChecked(False)
        done = _find_primary()
        if done is not None:
            done.click()
        QTimer.singleShot(300, app.exit)
        return

    if "安装失败" in st:
        print("  安装线程报错", flush=True)
        for w in _widgets():
            w.close()
        app.exit(1)
        return

    QTimer.singleShot(200, _tick)


def _fake_exec(*_a, **_k):
    QTimer.singleShot(700, _tick)
    return _orig_exec()


QApplication.exec = _fake_exec

print("== 启动安装向导 ==", flush=True)
code = S.run_gui()
print(f"  向导退出码 {code}，状态：{_state}", flush=True)

# ---------------------------------------------------------------- 验证
print("== 验证安装结果 ==", flush=True)
check("向导走到了「安装完成」", _state["finished"])

exe = os.path.join(TARGET, S.APP_EXE)
check(f"主程序已释放：{S.APP_EXE}", os.path.isfile(exe),
      f"{os.path.getsize(exe) / 1024 / 1024:.0f} MB" if os.path.isfile(exe) else "")
check("卸载程序已释放", os.path.isfile(os.path.join(TARGET, "uninstall.exe")))

n_files = sum(len(f) for _r, _d, f in os.walk(TARGET)) if os.path.isdir(TARGET) else 0
check("依赖文件数量合理", n_files > 40, f"{n_files} 个文件")

qt = os.path.join(TARGET, "_internal", "PySide6")
check("Qt 运行时已就位",
      os.path.isdir(qt) or os.path.isdir(os.path.join(TARGET, "PySide6")))

check("开始菜单快捷方式已创建",
      os.path.isfile(os.path.join(S.startmenu_dir(), f"{S.APP_NAME}.lnk")))
check("桌面快捷方式已创建",
      os.path.isfile(os.path.join(S.desktop_dir(), f"{S.APP_NAME}.lnk")))

try:
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                         r"Software\Microsoft\Windows\CurrentVersion\Uninstall\PicSprite")
    disp, _ = winreg.QueryValueEx(key, "DisplayName")
    loc, _ = winreg.QueryValueEx(key, "InstallLocation")
    winreg.CloseKey(key)
    check("卸载信息已登记", "看图精灵" in disp and loc == TARGET, disp)
except Exception as exc:  # noqa: BLE001
    check("卸载信息已登记", False, str(exc))

# ---------------------------------------------------------------- 清理
print("== 清理测试安装 ==", flush=True)
for fn in ("unregister", "remove_shortcuts"):
    try:
        getattr(S, fn)(TARGET) if fn == "unregister" else getattr(S, fn)()
    except Exception as exc:  # noqa: BLE001
        print(f"  {fn}: {exc}", flush=True)
shutil.rmtree(BASE, ignore_errors=True)
check("测试目录已清理", not os.path.isdir(BASE))

passed = sum(1 for _n, ok in RESULTS if ok)
print(f"\n通过 {passed}/{len(RESULTS)}")
failed = [n for n, ok in RESULTS if not ok]
if failed:
    print("失败项：" + "、".join(failed))
sys.exit(0 if not failed else 1)
