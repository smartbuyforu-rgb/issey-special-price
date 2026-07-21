@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ==============================================
echo INSTALL STANDARD PYTHON 3.12

echo This installs the normal GIL-enabled Python 3.12.
echo It can coexist with your current Python 3.13t.
echo ==============================================
echo.

where winget >nul 2>nul
if errorlevel 1 goto :manual

winget install --exact --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto :manual

echo.
echo [OK] Python 3.12 installation command completed.
echo Close this window, then run 01_INSTALL.bat again.
pause
exit /b 0

:manual
echo.
echo [INFO] Automatic installation was unavailable.
echo A Python download page will open.
echo Install standard Python 3.12, NOT the free-threaded option.
echo Enable the Python launcher and Add Python to PATH if offered.
start "" "https://www.python.org/downloads/windows/"
pause
exit /b 1
