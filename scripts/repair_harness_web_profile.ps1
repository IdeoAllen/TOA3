#Requires -Version 5.1
# 修复 Harness Web 组件（WorkBuddy / npm dsh 路径）：链接 profile node_modules
# 用法：powershell -ExecutionPolicy Bypass -File scripts\repair_harness_web_profile.ps1

$ErrorActionPreference = "Stop"

function Read-HarnessYaml {
  $paths = @(
    "$env:LOCALAPPDATA\YCZH-TOA3\config\harness.yml",
    "$env:LOCALAPPDATA\Programs\TOA3\config\harness.yml"
  )
  foreach ($p in $paths) {
    if (Test-Path $p) {
      return $p
    }
  }
  throw "未找到 harness.yml（请先运行 TOA3 并完成 Harness 路径登记）"
}

function Parse-YamlValue($text, $key) {
  if ($text -match "(?m)^\s*${key}:\s*(.+)$") {
    return $Matches[1].Trim().Trim("'").Trim('"')
  }
  return ""
}

$yamlPath = Read-HarnessYaml
$yaml = Get-Content $yamlPath -Raw -Encoding UTF8
$node = Parse-YamlValue $yaml "node_exe"
$dsh = Parse-YamlValue $yaml "dsh_bin"
$dshHome = Parse-YamlValue $yaml "dsh_home"

if (-not $node -or -not (Test-Path $node)) { throw "node_exe 无效: $node" }
if (-not $dsh -or -not (Test-Path $dsh)) { throw "dsh_bin 无效: $dsh" }
if (-not $dshHome) { throw "dsh_home 未配置" }

$dshPkg = Split-Path (Split-Path $dsh -Parent) -Parent
$vendored = Join-Path $dshPkg "node_modules"
$web = Join-Path $dshHome "profiles\web"
$link = Join-Path $web "node_modules"

if (-not (Test-Path $vendored)) { throw "未找到 dsh 内置组件: $vendored" }

New-Item -ItemType Directory -Force -Path $web | Out-Null

if (Test-Path $link) {
  cmd /c "rmdir `"$link`"" 2>$null
  if (Test-Path $link) {
    Remove-Item -LiteralPath $link -Recurse -Force -ErrorAction SilentlyContinue
  }
}

cmd /c "mklink /J `"$link`" `"$vendored`""
if (-not (Test-Path (Join-Path $link "@deepseek-ai\dsh-base"))) {
  throw "链接后仍缺少 dsh-base，请检查 WorkBuddy / dsh 安装"
}

Write-Host "OK: Web 组件已链接"
Write-Host "  profile: $web"
Write-Host "  -> $vendored"
Write-Host "请回到 TOA3 编码智能体，点「启动服务」。"
