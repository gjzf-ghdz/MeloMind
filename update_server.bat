@echo off
chcp 65001 >nul
title MeloMind 一键更新服务器
cd /d "%~dp0"
echo ==========================================
echo   MeloMind 一键更新 -> 47.99.92.14
echo   流程: 打包 -^> 上传 -^> 重启 -^> 验证
echo ==========================================
echo.
python update_server.py
echo.
pause
