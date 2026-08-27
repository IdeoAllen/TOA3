@echo off
chcp 65001 >nul
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%.."
cd /d "%PROJECT_ROOT%"

echo.
echo   TOA3 Windows 打包（对齐 TOA2 packaging-app）
echo   =============================================
echo.

python --version >nul 2>nul
if %errorlevel% neq 0 (
  echo [错误] 未找到 Python
  pause
  exit /b 1
)

python -m pip show pyinstaller >nul 2>nul
if %errorlevel% neq 0 (
  echo 正在安装 pyinstaller ...
  python -m pip install pyinstaller
)

echo 开始打包 TOA3 ...
python packaging\build_windows.py --clean --msi
if %errorlevel% neq 0 (
  echo.
  echo [失败] 打包未完成
  pause
  exit /b 1
)

echo.
echo 完成。正式分发：
echo   packaging\dist\TOA3-Setup-v*.exe
echo.
pause
