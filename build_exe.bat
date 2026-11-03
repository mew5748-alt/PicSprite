@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo   看图精灵 - 打包为独立 exe
echo ============================================
echo.

python -c "import PyInstaller" >nul 2>nul
if not %errorlevel%==0 (
    echo 正在安装 PyInstaller ...
    python -m pip install pyinstaller
    if not %errorlevel%==0 goto :fail
)

echo 正在打包（首次约需 1-3 分钟）...
python -m PyInstaller --noconfirm --clean --windowed ^
    --name "看图精灵" ^
    --icon "assets\app.ico" ^
    --add-data "assets;assets" ^
    --exclude-module PySide6.QtWebEngineCore ^
    --exclude-module PySide6.QtWebEngineWidgets ^
    --exclude-module PySide6.QtQuick ^
    --exclude-module PySide6.QtQml ^
    --exclude-module PySide6.Qt3DCore ^
    --exclude-module tkinter ^
    main.py
if not %errorlevel%==0 goto :fail

echo.
echo 打包完成！exe 位于： dist\看图精灵\看图精灵.exe
echo 把整个 dist\看图精灵 文件夹复制走即可在没有 Python 的电脑上运行。
pause
exit /b 0

:fail
echo.
echo 打包失败，请检查上方错误信息。
pause
exit /b 1
