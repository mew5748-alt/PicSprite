# -*- coding: utf-8 -*-
"""一键构建 Windows 安装包。

流程：
    1. PyInstaller 打包主程序（onedir，启动快）
    2. 把整个程序目录压成 payload.zip
    3. PyInstaller 打包安装向导（onefile，内嵌 payload.zip）
       -> dist/看图精灵-Setup-<版本>.exe

用法：
    python tools/build_release.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from viewer.config import APP_NAME, APP_VERSION  # noqa: E402

BUILD = os.path.join(ROOT, "build")
DIST = os.path.join(ROOT, "dist")
# 每次构建用全新目录，PyInstaller 就不会去删上一次的产物
RUN_DIR = os.path.join(BUILD, f"run-{int(time.time())}")
APP_DIR = os.path.join(RUN_DIR, "app", APP_NAME)
PAYLOAD = os.path.join(RUN_DIR, "payload.zip")
SETUP_NAME = f"{APP_NAME}-Setup-{APP_VERSION}"

# 安装向导只需要 QtCore/QtGui/QtWidgets，其余 Qt 模块一律不打包
SETUP_EXCLUDES = [
    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtPdf", "PySide6.Qt3DCore", "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets", "PySide6.QtDataVisualization", "PySide6.QtOpenGL",
    "PySide6.QtSvg", "PySide6.QtPrintSupport", "numpy", "matplotlib",
]

APP_EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQuick",
    "PySide6.QtQml", "PySide6.Qt3DCore", "PySide6.QtMultimedia", "PySide6.QtCharts",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtPdf", "PySide6.QtDataVisualization",
    "tkinter", "numpy", "matplotlib",
]


def run(cmd: list) -> None:
    print("»", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def step(msg: str) -> None:
    print(f"\n=== {msg} ===", flush=True)


def prepare() -> None:
    step("准备构建目录")
    os.makedirs(RUN_DIR, exist_ok=True)
    os.makedirs(DIST, exist_ok=True)
    print("   ", RUN_DIR, flush=True)


def build_app() -> None:
    step("打包主程序（onedir）")
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--windowed", "--name", APP_NAME,
           "--icon", os.path.join(ROOT, "assets", "app.ico"),
           "--distpath", os.path.join(RUN_DIR, "app"),
           "--workpath", os.path.join(RUN_DIR, "work"),
           "--specpath", RUN_DIR]
    for m in APP_EXCLUDES:
        cmd += ["--exclude-module", m]
    cmd.append(os.path.join(ROOT, "main.py"))
    run(cmd)
    assert os.path.exists(os.path.join(APP_DIR, APP_NAME + ".exe")), "主程序打包失败"


def make_payload() -> None:
    step("压缩程序文件")
    count = 0
    with zipfile.ZipFile(PAYLOAD, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for root, _dirs, files in os.walk(APP_DIR):
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, APP_DIR)
                z.write(full, rel)
                count += 1
    mb = os.path.getsize(PAYLOAD) / 1024 / 1024
    print(f"   {count} 个文件 -> payload.zip  {mb:.1f} MB", flush=True)


def build_setup() -> None:
    step("打包安装向导（onefile）")
    os.makedirs(DIST, exist_ok=True)
    ico = os.path.join(ROOT, "assets", "app.ico")
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--onefile", "--windowed", "--name", SETUP_NAME,
           "--icon", ico,
           "--add-data", f"{PAYLOAD}{os.pathsep}.",
           "--add-data", f"{ico}{os.pathsep}.",
           "--distpath", DIST,
           "--workpath", os.path.join(RUN_DIR, "setup"),
           "--specpath", os.path.join(RUN_DIR, "setup")]
    for m in SETUP_EXCLUDES:
        cmd += ["--exclude-module", m]
    cmd += [
           os.path.join(ROOT, "installer", "setup_main.py")]
    run(cmd)


def main() -> None:
    prepare()
    build_app()
    make_payload()
    build_setup()
    exe = os.path.join(DIST, SETUP_NAME + ".exe")
    print(f"\n完成：{exe}  {os.path.getsize(exe) / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
