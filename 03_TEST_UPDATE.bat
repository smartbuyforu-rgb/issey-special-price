@echo off
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul
set "PYTHONUTF8=1"

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Run 01_INSTALL.bat first.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" special_price_catalog.py collect
set "RC=%ERRORLEVEL%"

if "%RC%"=="0" (
  echo.
  echo [OK] Collection completed. Opening index.html...
  start "" "%CD%\index.html"
) else (
  echo.
  echo [ERROR] Collection failed.
  echo Run 02_LOGIN.bat again, or run 07_DIAGNOSE.bat.
)

pause
exit /b %RC%
