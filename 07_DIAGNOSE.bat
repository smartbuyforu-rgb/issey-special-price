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

".venv\Scripts\python.exe" special_price_catalog.py diagnose
set "RC=%ERRORLEVEL%"
echo.
echo Debug files are saved in the private folder:
echo   debug_collection.html
echo   debug_collection.png
echo   debug_info.json
echo These files are excluded from GitHub.
pause
exit /b %RC%
