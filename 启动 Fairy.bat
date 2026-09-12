@echo off
cd /d "%~dp0"

REM Kill leftover electron.exe before launching to free the singleton lock
REM (a previous crashed instance can hold the lock and silently block startup).
taskkill /F /IM electron.exe /T 2>nul >nul
timeout /t 1 /nobreak >nul

"%~dp0node_modules\electron\dist\electron.exe" . %*
set RC=%ERRORLEVEL%

if not "%RC%"=="0" (
    echo.
    echo ============================================================
    echo Fairy failed to start. Exit code: %RC%
    echo ============================================================
    echo.
    echo Common causes:
    echo   1. GPU process crashed - try adding --disable-gpu
    echo   2. Electron binary incomplete - run:
    echo        ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/ node node_modules\electron\install.js
    echo   3. Stale electron.exe holding files - retry (this bat now self-cleans)
    echo.
    pause
)
exit /b %RC%