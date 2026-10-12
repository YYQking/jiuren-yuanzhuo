@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONPATH=%~dp0;%~dp0.qt-build-runtime"
set "PY=C:\Users\14726\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

echo 正在启动开发版（含最新代码改动，不是桌面那个旧 EXE）...
echo.
echo 启动后请先看大厅的集成状态提示：
echo   显示「真实模型 deepseek-chat」= 真的在用 DeepSeek
echo   显示「离线模拟」或「未允许真实模型」= 没连上模型，这一场测不出效果
echo.

"%PY%" app.py

echo.
echo 程序已退出，返回码 %ERRORLEVEL%
pause
