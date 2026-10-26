# 本地开发：启动 TOA Cloud（授权 + 版本 + 运营台）
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"

if (-not $env:TOA_CLOUD_ADMIN_PASSWORD) {
    $env:TOA_CLOUD_ADMIN_PASSWORD = "dev-admin-change-me"
}
if (-not $env:TOA_CLOUD_ADMIN_USER) {
    $env:TOA_CLOUD_ADMIN_USER = "admin"
}

Write-Host "TOA Cloud -> http://127.0.0.1:8090/admin/"
Write-Host "License API -> http://127.0.0.1:8090/api/toa-license"
Write-Host "Manifest    -> http://127.0.0.1:8090/api/toa/releases/manifest?product=TOA3&channel=stable"

Set-Location $Backend
python -m uvicorn main:app --host 127.0.0.1 --port 8090 --reload
