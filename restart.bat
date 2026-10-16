@echo off
chcp 65001 >nul
title MeloMind Restart

echo Stopping old server...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 .*LISTENING"') do (
    echo   Killing PID: %%a
    taskkill /F /PID %%a >nul 2>&1
)
taskkill /F /FI "WINDOWTITLE eq MeloMind*" >nul 2>&1

timeout /t 2 /nobreak >nul

echo Starting MeloMind server...
cd /d "%~dp0backend"
if exist __pycache__ rmdir /s /q __pycache__
python server.py
pause