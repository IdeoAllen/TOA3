# TOA3 启动脚本（Windows）
# 用法：在资源管理器双击，或 PowerShell 中执行
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:TOA_ENV = if ($env:TOA_ENV) { $env:TOA_ENV } else { "development" }

function Test-ToaPython([string]$Exe) {
    if (-not (Test-Path $Exe)) { return $false }
    & $Exe -c "import PySide6" 2>$null
    return ($LASTEXITCODE -eq 0)
}

function Stop-StaleToa3 {
    # 避免 Hermes 父进程 + 旧实例叠加双 python -m app.main
    $killed = 0
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match '^(python|pythonw)(\.exe)?$' -and
            $_.CommandLine -and
            ($_.CommandLine -match '-m\s+app\.main' -or $_.CommandLine -match '["'']app\.main["'']')
        } |
        ForEach-Object {
            try {
                Write-Host "结束旧实例 PID $($_.ProcessId)"
                Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
                $script:killed++
            } catch {
                Write-Host "无法结束 PID $($_.ProcessId): $_"
            }
        }
    if ($killed -gt 0) {
        Start-Sleep -Milliseconds 400
    }
}

$candidates = @(
    (Get-Command python -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
    "$env:LOCALAPPDATA\hermes\hermes-agent\venv\Scripts\python.exe",
    "$env:USERPROFILE\.venv\Scripts\python.exe",
    "python"
) | Where-Object { $_ }

$py = $null
foreach ($c in $candidates) {
    if (Test-ToaPython $c) { $py = $c; break }
}
if (-not $py) {
    Write-Host "未找到已安装 PySide6 的 Python。请先: pip install -r requirements.txt"
    pause
    exit 1
}

Stop-StaleToa3

Write-Host "启动 TOA3 ..."
Write-Host "  Python: $py"
Write-Host "  目录:   $Root"
& $py -m app.main
if ($LASTEXITCODE -ne 0) {
    Write-Host "退出码: $LASTEXITCODE"
    pause
}
