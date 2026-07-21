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

title ISSEY SPECIAL PRICE AUTO UPDATE
".venv\Scripts\python.exe" special_price_catalog.py monitor --publish
set "RC=%ERRORLEVEL%"
echo.
echo Auto update stopped.
pause
exit /b %RC%
