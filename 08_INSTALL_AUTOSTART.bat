@echo off
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul

powershell -NoProfile -ExecutionPolicy Bypass -Command "$startup=[Environment]::GetFolderPath('Startup'); $target=Join-Path '%~dp0' '05_START_AUTO_UPDATE.bat'; $ws=New-Object -ComObject WScript.Shell; $link=Join-Path $startup 'ISSEY Special Price Catalog.lnk'; $lnk=$ws.CreateShortcut($link); $lnk.TargetPath=$target; $lnk.WorkingDirectory='%~dp0'; $lnk.WindowStyle=7; $lnk.Save(); Write-Host '[OK] Startup shortcut created.'"

if errorlevel 1 (
  echo [ERROR] Failed to create the startup shortcut.
  pause
  exit /b 1
)

pause
exit /b 0
