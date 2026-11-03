@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem 优先用 pythonw 启动，避免弹出黑色控制台窗口
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0main.py" %*
) else (
    python "%~dp0main.py" %*
)
