# -*- coding: utf-8 -*-
"""生成 TOA3 安装/升级/卸载入口（对齐 TOA2 make_upgrade_launcher.py）。"""
from __future__ import annotations

from pathlib import Path


def write_upgrade_scripts(dist_dir: str, version: str, app_short: str = "TOA3") -> list[str]:
    dist = Path(dist_dir)
    dist.mkdir(parents=True, exist_ok=True)

    setup_name = f"{app_short}-Setup-v{version}.exe"
    folder_name = f"{app_short}-v{version}-win64"
    exe_name = f"{app_short}.exe"
    install_dir = "TOA3"

    ps1_name = f"{app_short}-upgrade.ps1"
    bat_name = f"{app_short}-upgrade.bat"
    uninstall_ps1 = f"{app_short}-uninstall.ps1"
    uninstall_bat = f"{app_short}-uninstall.bat"

    ps1 = dist / ps1_name
    bat = dist / bat_name

    ps1.write_text(
        f"""#Requires -Version 5.1
# TOA3 install/upgrade via official setup.exe (no admin by default)
$ErrorActionPreference = "Stop"
$Version = "{version}"
$SetupName = "{setup_name}"
$ExeName = "{exe_name}"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogFile = Join-Path $env:TEMP ("TOA3-setup-" + $Version + ".log")
$License = $env:TOA_LICENSE

function Write-Step([string]$msg) {{
  $line = ("[setup] " + $msg)
  Write-Host $line
  try {{ Add-Content -Path $LogFile -Value $line -Encoding UTF8 }} catch {{}}
}}

function Get-SetupExe {{
  $p = Join-Path $Here $SetupName
  if (Test-Path $p) {{ return $p }}
  $hit = Get-ChildItem $Here -Filter "{app_short}-Setup-v*.exe" -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if ($hit) {{ return $hit.FullName }}
  return $null
}}

try {{
  try {{ Set-Content -Path $LogFile -Value ("TOA3 setup " + $Version + " " + (Get-Date)) -Encoding UTF8 }} catch {{}}
  Write-Host ""
  Write-Host "========================================"
  Write-Host "  TOA3 Setup / Upgrade  v$Version"
  Write-Host "  No admin required by default"
  Write-Host "  Activate license inside the app after install"
  Write-Host "========================================"
  Write-Host ""
  $setup = Get-SetupExe
  if (-not $setup) {{ throw "Setup not found: $SetupName" }}

  $targetDir = Join-Path $env:LOCALAPPDATA "Programs\\{install_dir}"
  Get-Process -Name {app_short} -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep -Milliseconds 500

  $args = @(
    "/CURRENTUSER",
    "/DIR=`"$targetDir`"",
    "/NORESTART",
    "/CLOSEAPPLICATIONS",
    "/FORCECLOSEAPPLICATIONS",
    "/LOG=`"$LogFile`"",
    "/TASKS=desktopicon"
  )
  if ($License) {{
    $args = @("/VERYSILENT") + $args + @("/LICENSE=$License")
    Write-Step "Silent install with optional TOA_LICENSE"
  }} else {{
    Write-Step "Launching interactive setup (no license required)"
  }}

  $p = Start-Process -FilePath $setup -ArgumentList $args -Wait -PassThru
  if ($p.ExitCode -ne 0) {{ throw ("Setup exit code " + $p.ExitCode + ", log: " + $LogFile) }}
  Write-Step "Done. Version $Version"
  Write-Step ("Log: " + $LogFile)
  exit 0
}} catch {{
  Write-Host ("FAIL: " + $_.Exception.Message) -ForegroundColor Red
  try {{ Add-Content -Path $LogFile -Value ("FAIL: " + $_.Exception.Message) -Encoding UTF8 }} catch {{}}
  Pause
  exit 1
}}
""",
        encoding="utf-8",
    )

    bat.write_text(
        f"""@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0{ps1_name}"
if errorlevel 1 (
  echo.
  echo Install/Upgrade failed.
  pause
)
""",
        encoding="ascii",
        errors="strict",
    )

    (dist / uninstall_ps1).write_text(
        f"""#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$AppPattern = "TOA3|运营宝|Training Operations Assistant 3"
Write-Host "Stopping TOA3 if running..."
Get-Process -Name {app_short} -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500
Write-Host "Looking for installed TOA3..."
$apps = Get-ItemProperty @(
  "HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*",
  "HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*",
  "HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*"
) -ErrorAction SilentlyContinue | Where-Object {{
  $_.DisplayName -and ($_.DisplayName -match $AppPattern)
}}
if (-not $apps) {{
  Write-Host "Not found in Apps list. Use Windows Settings -> Apps to uninstall."
  Pause
  exit 1
}}
foreach ($a in $apps) {{
  Write-Host ("Uninstall: " + $a.DisplayName + " " + $a.DisplayVersion)
  $quiet = [string]$a.QuietUninstallString
  $u = [string]$a.UninstallString
  if ($quiet) {{ cmd /c $quiet | Out-Null }}
  elseif ($u -match 'unins\\d+\\.exe') {{
    $exe = ($u -replace '"','').Trim()
    if ($exe -match '^(.*unins\\d+\\.exe)') {{ $exe = $Matches[1] }}
    Start-Process -FilePath $exe -ArgumentList "/SILENT","/NORESTART","/SUPPRESSMSGBOXES","/FORCECLOSEAPPLICATIONS" -Wait
  }} else {{ cmd /c $u | Out-Null }}
}}
Write-Host "Uninstall finished."
""",
        encoding="utf-8",
    )

    (dist / uninstall_bat).write_text(
        f"""@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0{uninstall_ps1}"
if errorlevel 1 pause
""",
        encoding="ascii",
        errors="strict",
    )

    readme = dist / "安装说明.txt"
    readme.write_text(
        f"""TOA3 赋能培训运营助手（运营宝）v{version}

【安装】
  双击「{setup_name}」
  - 默认不需要管理员权限
  - 安装时无需授权码
  - 装好后启动软件，向管理员索取 TOA2 授权码并联网激活
  - 到期或被停用：无需卸载，申请新码后重新激活即可
  - 安装目录：%LOCALAPPDATA%\\Programs\\TOA3（与 TOA2 可并存）

【升级】
  再运行新版本 {setup_name} 即可（同 AppId 自动覆盖）

【卸载】
  Windows「设置 → 应用」搜索 TOA3 / 运营宝
  或开始菜单 Uninstall TOA3
  或双击 {uninstall_bat}

【可选：静默安装并顺便激活】
  set TOA_LICENSE=TOA2-你的授权码
  {bat_name}

【其他】
  {folder_name}\\   构建产物目录（不要手动拷贝安装）
""",
        encoding="utf-8",
    )
    (dist / "升级说明.txt").write_text(readme.read_text(encoding="utf-8"), encoding="utf-8")

    return [str(bat), str(ps1), str(dist / uninstall_bat), str(dist / uninstall_ps1), str(readme)]


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    print("\n".join(write_upgrade_scripts(str(here / "dist"), "3.0.0")))
