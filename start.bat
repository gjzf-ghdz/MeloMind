@echo off
chcp 65001 >nul
title MeloMind Backend Server
cd /d "%~dp0backend"
echo ========================================
echo   MeloMind Backend Server
echo   访问地址: http://localhost:8000
echo   按 Ctrl+C 停止服务
echo ========================================
echo.
python server.py
echo.
echo 服务已停止，按任意键关闭窗口...
pause >nul
