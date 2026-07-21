@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONUTF8=1"

echo ==============================================
echo ISSEY SPECIAL PRICE CATALOG - INSTALL v1.2
echo ==============================================
echo.

echo [1/5] Finding a compatible standard Python...
set "PY_CMD="

rem Prefer standard CPython 3.12, then 3.13, then 3.11.
rem Free-threaded builds such as cp313t are intentionally rejected.
py -3.12 -c "import sys,sysconfig; raise SystemExit(0 if sys.version_info[:2]==(3,12) and not bool(sysconfig.get_config_var('Py_GIL_DISABLED')) else 1)" >nul 2>nul
if not errorlevel 1 set "PY_CMD=py -3.12"

if not defined PY_CMD (
  py -3.13 -c "import sys,sysconfig; raise SystemExit(0 if sys.version_info[:2]==(3,13) and not bool(sysconfig.get_config_var('Py_GIL_DISABLED')) else 1)" >nul 2>nul
  if not errorlevel 1 set "PY_CMD=py -3.13"
)

if not defined PY_CMD (
  py -3.11 -c "import sys,sysconfig; raise SystemExit(0 if sys.version_info[:2]==(3,11) and not bool(sysconfig.get_config_var('Py_GIL_DISABLED')) else 1)" >nul 2>nul
  if not errorlevel 1 set "PY_CMD=py -3.11"
)

if not defined PY_CMD (
  where python >nul 2>nul
  if not errorlevel 1 (
    python -c "import sys,sysconfig; ok=sys.version_info[:2] in ((3,11),(3,12),(3,13)) and not bool(sysconfig.get_config_var('Py_GIL_DISABLED')); raise SystemExit(0 if ok else 1)" >nul 2>nul
    if not errorlevel 1 set "PY_CMD=python"
  )
)

if not defined PY_CMD goto :python_required

for /f "delims=" %%V in ('%PY_CMD% -c "import sys; print(sys.version.split()[0])"') do set "PY_VERSION=%%V"
for /f "delims=" %%E in ('%PY_CMD% -c "import sys; print(sys.executable)"') do set "PY_EXE=%%E"
echo [OK] Python %PY_VERSION%
echo      %PY_EXE%

echo [2/5] Checking the existing virtual environment...
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys,sysconfig; ok=sys.version_info[:2] in ((3,11),(3,12),(3,13)) and not bool(sysconfig.get_config_var('Py_GIL_DISABLED')); raise SystemExit(0 if ok else 1)" >nul 2>nul
  if errorlevel 1 (
    echo [INFO] Removing an incompatible virtual environment...
    rmdir /s /q ".venv"
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo [3/5] Creating a new virtual environment...
  %PY_CMD% -m venv .venv
  if errorlevel 1 goto :error
) else (
  echo [3/5] Existing compatible virtual environment found.
)

echo [4/5] Installing Python packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install --only-binary=:all: -r requirements.txt
if errorlevel 1 goto :binary_error

echo [5/5] Installing Playwright Chromium...
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto :error

echo.
echo [OK] Installation completed.
echo Next, run 02_LOGIN.bat
pause
exit /b 0

:python_required
echo.
echo [ERROR] A compatible standard Python was not found.
echo Your current Python is probably a free-threaded build such as 3.13t.
echo Run 00_INSTALL_PYTHON_312.bat, then run 01_INSTALL.bat again.
echo.
pause
exit /b 2

:binary_error
echo.
echo [ERROR] A prebuilt package could not be installed.
echo Do not install Microsoft C++ Build Tools for this project.
echo Run 00_INSTALL_PYTHON_312.bat, then delete .venv and retry.
pause
exit /b 3

:error
echo.
echo [ERROR] Installation failed. Review the messages above.
pause
exit /b 1
