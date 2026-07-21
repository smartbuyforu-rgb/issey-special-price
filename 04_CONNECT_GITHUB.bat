@echo off
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul

echo ==============================================
echo CONNECT TO A NEW GITHUB REPOSITORY
echo ==============================================

where git >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Git for Windows was not found.
  echo Install it from: https://git-scm.com/download/win
  pause
  exit /b 1
)

echo Create an empty PUBLIC GitHub repository first.
echo Do not add README, .gitignore, or License on GitHub.
echo Example: https://github.com/USERNAME/issey-special-price.git
echo.
set /p "REPO_URL=Paste the new repository HTTPS URL: "

if not defined REPO_URL (
  echo [ERROR] Repository URL is empty.
  pause
  exit /b 1
)

if not exist ".git" git init
if errorlevel 1 goto :error

git branch -M main
for /f "delims=" %%A in ('git remote 2^>nul') do if /I "%%A"=="origin" git remote remove origin
git remote add origin "%REPO_URL%"
if errorlevel 1 goto :error

git config user.name >nul 2>nul
if errorlevel 1 git config user.name "special-price-catalog"
git config user.email >nul 2>nul
if errorlevel 1 git config user.email "catalog@users.noreply.github.com"

git add .
git commit -m "Initial SPECIAL PRICE catalog"
if errorlevel 1 (
  git status --porcelain | findstr . >nul
  if not errorlevel 1 goto :error
)

echo.
echo Pushing to GitHub. Approve the browser sign-in if requested.
git push -u origin main
if errorlevel 1 goto :error

echo.
echo [OK] GitHub connection completed.
echo Enable GitHub Pages from Settings - Pages - main - root.
pause
exit /b 0

:error
echo.
echo [ERROR] GitHub connection failed. Review the messages above.
pause
exit /b 1
