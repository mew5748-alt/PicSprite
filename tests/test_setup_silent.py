# -*- coding: utf-8 -*-
"""安装包端到端验证：静默安装 -> 检查文件/快捷方式/注册表 -> 运行 -> 静默卸载。

用法：python tests/test_setup_silent.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import winreg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from viewer.config import APP_NAME, APP_VERSION  # noqa: E402

EXE = os.path.join(ROOT, "dist", f"{APP_NAME}-Setup-{APP_VERSION}.exe")
TARGET = os.path.join(os.environ["LOCALAPPDATA"], "Programs", "PicSprite")
STARTMENU = os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu",
                         "Programs")
UNINST_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\PicSprite"
NO_WINDOW = 0x08000000

passed, failed = [], []


def check(name: str, ok: bool, detail: str = "") -> None:
    (passed if ok else failed).append(name)
    print(f"{'  OK ' if ok else '  ✗  '} {name}{('  ' + detail) if detail else ''}")


def key_exists(path: str) -> bool:
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, path))
        return True
    except OSError:
        return False


def read_value(path: str, name: str) -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
            return str(winreg.QueryValueEx(k, name)[0])
    except OSError:
        return ""


def value_exists(path: str, name: str) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
            winreg.QueryValueEx(k, name)
            return True
    except OSError:
        return False


def procs(name: str) -> int:
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH"],
                         capture_output=True, creationflags=NO_WINDOW)
    return out.stdout.count(name.encode("gbk", "ignore"))


print(f"安装包：{EXE}  ({os.path.getsize(EXE) / 1024 / 1024:.1f} MB)\n")

# ---------------------------------------------------------------- 预清理
# 上一轮测试或用户手动安装可能留下快捷方式。Inno Setup 发现目标相同的快捷方式
# 会跳过创建，卸载时也就不在它的清单里，会让「已清理」检查假失败。
for _name in (f"{APP_NAME}.lnk", "卸载看图精灵.lnk"):
    _p = os.path.join(STARTMENU, _name)
    if os.path.exists(_p):
        try:
            os.remove(_p)
            print(f"[0] 清理残留快捷方式：{_p}")
        except OSError:
            pass

# ---------------------------------------------------------------- 安装
print("[1] 静默安装")
t0 = time.time()
subprocess.run([EXE, "/S"], timeout=600)
time.sleep(1.5)
check("安装程序已退出", procs(f"{APP_NAME}-Setup-{APP_VERSION}.exe") == 0)
check("安装目录已建立", os.path.isdir(TARGET), TARGET)
check("主程序存在", os.path.exists(os.path.join(TARGET, f"{APP_NAME}.exe")))
check("卸载程序存在", os.path.exists(os.path.join(TARGET, "uninstall.exe")))
check("运行时文件齐全", os.path.isdir(os.path.join(TARGET, "_internal")))
check("开始菜单快捷方式", os.path.exists(os.path.join(STARTMENU, f"{APP_NAME}.lnk")))
check("卸载快捷方式", os.path.exists(os.path.join(STARTMENU, "卸载看图精灵.lnk")))
check("注册表卸载项", key_exists(UNINST_KEY))
check("卸载命令正确",
      os.path.join(TARGET, "uninstall.exe") in read_value(UNINST_KEY, "UninstallString"),
      read_value(UNINST_KEY, "UninstallString"))
check("版本号写入", read_value(UNINST_KEY, "DisplayVersion") == APP_VERSION,
      read_value(UNINST_KEY, "DisplayVersion"))
size_kb = int(read_value(UNINST_KEY, "EstimatedSize") or 0)
check("安装体积已统计", size_kb > 50_000, f"{size_kb / 1024:.0f} MB")

# 关联过的扩展名都要出现在“打开方式”候选里。HEIC 曾经漏注册，导致双击打不开，
# 加这条回归检查，避免再漏
for _ext in (".jpg", ".png", ".heic", ".heif"):
    _path = rf"Software\Classes\{_ext}\OpenWithProgids"
    check(f"打开方式含 {_ext}", value_exists(_path, "PicSprite.Image"))
check("ProgID 声明支持 HEIC",
      value_exists(r"Software\Classes\PicSprite.Image\SupportedTypes", ".heic"))
print(f"    耗时 {time.time() - t0:.1f}s\n")

# ---------------------------------------------------------------- 运行
print("[2] 运行已安装的程序")
launched = subprocess.Popen([os.path.join(TARGET, f"{APP_NAME}.exe")])
time.sleep(6)
check("程序可启动", launched.poll() is None)
# onefile 程序会派生真正干活的子进程，只 kill 父进程会留下孤儿占住安装目录
subprocess.run(["taskkill", "/F", "/T", "/PID", str(launched.pid)],
               capture_output=True, creationflags=NO_WINDOW)
try:
    launched.wait(5)
except Exception:
    pass
time.sleep(1)

# ---------------------------------------------------------------- 卸载
print("[3] 静默卸载")
subprocess.run([os.path.join(TARGET, "uninstall.exe"), "/uninstall", "/S"], timeout=120)
link = os.path.join(STARTMENU, f"{APP_NAME}.lnk")
deadline = time.time() + 30
while time.time() < deadline and (os.path.isdir(TARGET) or os.path.exists(link)):
    time.sleep(1)
check("安装目录已删除（延迟清理）", not os.path.isdir(TARGET))
check("开始菜单快捷方式已清理", not os.path.exists(link))
check("注册表卸载项已清理", not key_exists(UNINST_KEY))
check("打开方式注册项已清理",
      not key_exists(r"Software\Classes\PicSprite.Image"))
check("HEIC 打开方式项已清理",
      not value_exists(r"Software\Classes\.heic\OpenWithProgids", "PicSprite.Image"))

print(f"\n通过 {len(passed)} 项，失败 {len(failed)} 项")
if failed:
    print("失败项：" + "、".join(failed))
    sys.exit(1)
