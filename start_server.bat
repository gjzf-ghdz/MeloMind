@echo off
chcp 65001 >nul
title MeloMind Music Recommender

echo ============================================
echo   Launching MeloMind music recommender...
echo ============================================

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 .*LISTENING"') do (
    echo   Killing old process PID: %%a
    taskkill /F /PID %%a >nul 2>&1
)

timeout /t 1 /nobreak >nul

echo.
echo   Starting MeloMind server...
start "MeloMind" python "%~dp0backend\server.py"
timeout /t 3 /nobreak >nul

echo   Server URL: http://localhost:8000
echo   Browser will open automatically...
echo.
start http://localhost:8000
echo Press any key to close this window (server keeps running)
pause