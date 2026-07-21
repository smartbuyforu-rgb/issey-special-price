@echo off
setlocal EnableExtensions
chcp 65001 >nul

powershell -NoProfile -ExecutionPolicy Bypass -Command "$link=Join-Path ([Environment]::GetFolderPath('Startup')) 'ISSEY Special Price Catalog.lnk'; if(Test-Path $link){Remove-Item $link -Force; Write-Host '[OK] Startup shortcut removed.'}else{Write-Host '[INFO] No startup shortcut was found.'}"

if errorlevel 1 (
  echo [ERROR] Failed to remove the startup shortcut.
  pause
  exit /b 1
)

pause
exit /b 0
