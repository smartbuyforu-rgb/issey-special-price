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

".venv\Scripts\python.exe" special_price_catalog.py login
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo [ERROR] Login profile was not saved. Review the messages above.
pause
exit /b %RC%
