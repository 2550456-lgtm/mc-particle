@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动粒子墙工作台...
start "particle-wall-server" cmd /c "python server.py"
timeout /t 2 >nul
start "" http://127.0.0.1:8765
echo.
echo 服务窗口已打开，关闭那个窗口即停止服务。
echo 浏览器地址： http://127.0.0.1:8765
timeout /t 3 >nul
