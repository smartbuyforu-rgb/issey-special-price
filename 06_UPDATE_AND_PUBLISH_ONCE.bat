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

".venv\Scripts\python.exe" special_price_catalog.py collect --publish
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%
