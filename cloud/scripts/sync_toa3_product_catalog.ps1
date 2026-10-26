# 从 TOA3 同步产品目录（功能包 + 菜单 module 索引）
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Toa3 = Split-Path -Parent $Root

Copy-Item (Join-Path $Toa3 "config\feature_packs.yml") (Join-Path $Root "config\feature_packs.yml") -Force
Write-Host "Synced feature_packs.yml"

Push-Location $Toa3
python scripts/export_menu_catalog.py
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "export_menu_catalog failed" }
Pop-Location

Write-Host "Pruning product plans to tiyan + local_free..."
Push-Location $Root
& python scripts/prune_product_plans.py
Pop-Location

Write-Host "Product catalog synced -> cloud/config/"
