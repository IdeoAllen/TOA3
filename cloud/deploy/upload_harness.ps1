# 上传 Harness 双包到 toa-service /download/（与 TOA Setup 分离 · 禁止打进超级包）
# 对标：upload_installer.ps1 · 服务器 /opt/toa-cloud/download/
#
# 两段式（SOP-04 §5）：
#   ① 本脚本只上传 zip（+ .sha256 / meta json）→ 停住等人确认「切配置」
#   ② 主理人确认后：python scripts/sync_harness_bundles.py --from-dist --version X --apply --verify-cdn
#
param(
  [Parameter(Mandatory = $true)]
  [string]$BundleVersion,
  [string]$Server = "121.43.127.159",
  [string]$User = "root",
  [string]$DownloadDir = "/opt/toa-cloud/download",
  [string]$PublicBaseUrl = "https://toa-service.yczh.tech",
  [string]$DistDir = ""
)

$ErrorActionPreference = "Stop"
$Toa3Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$ver = $BundleVersion.Trim()
if (-not $DistDir) {
  $DistDir = Join-Path $Toa3Root "packaging\dist\harness"
}
if (-not (Test-Path $DistDir)) {
  throw "找不到构包目录: $DistDir（请先 python scripts/build_harness_prefab.py）"
}

$names = @(
  "harness-official-$ver.zip",
  "harness-prefab-$ver.zip"
)
$optional = @(
  "harness-official-$ver.zip.sha256",
  "harness-prefab-$ver.zip.sha256",
  "harness-bundles-$ver.json"
)

$sshTarget = "${User}@${Server}"
$remoteDir = $DownloadDir
$cdnBase = "$($PublicBaseUrl.TrimEnd('/'))/download"

foreach ($name in $names) {
  $local = Join-Path $DistDir $name
  if (-not (Test-Path $local)) {
    throw "缺少必传文件: $local"
  }
  $mb = '{0:N1}' -f ((Get-Item $local).Length / 1MB)
  Write-Host "==> 上传 $name ($mb MB)" -ForegroundColor Cyan
  scp $local "${sshTarget}:${remoteDir}/$name"
  if ($LASTEXITCODE -ne 0) { throw "上传失败: $name" }
}

foreach ($name in $optional) {
  $local = Join-Path $DistDir $name
  if (-not (Test-Path $local)) { continue }
  Write-Host "==> 上传旁证 $name" -ForegroundColor DarkCyan
  scp $local "${sshTarget}:${remoteDir}/$name"
  if ($LASTEXITCODE -ne 0) { throw "上传失败: $name" }
}

Write-Host "==> HEAD 校验直链" -ForegroundColor Cyan
foreach ($name in $names) {
  $url = "$cdnBase/$name"
  try {
    $resp = Invoke-WebRequest -Uri $url -Method Head -UseBasicParsing -TimeoutSec 40
    $len = [int64]($resp.Headers["Content-Length"] | Select-Object -First 1)
    if ($resp.StatusCode -notin 200, 206) {
      throw "HTTP $($resp.StatusCode)"
    }
    if ($len -lt 50MB) {
      throw "Content-Length 过小: $len"
    }
    Write-Host "  OK $name  HTTP $($resp.StatusCode)  size=$len" -ForegroundColor Green
  } catch {
    throw "直链不可达 $url : $($_.Exception.Message)"
  }
}

Write-Host ""
Write-Host "上传完成。下一步（人工闸门 · 切配置 = 用户立刻下到新包）：" -ForegroundColor Green
Write-Host "  主理人确认后执行：" -ForegroundColor White
Write-Host "  cd TOA3" -ForegroundColor Yellow
Write-Host "  python scripts/sync_harness_bundles.py --from-dist --version $ver --apply --verify-cdn" -ForegroundColor Yellow
Write-Host "  （可选）再加 --commit" -ForegroundColor DarkGray
Write-Host "  官方: $cdnBase/harness-official-$ver.zip" -ForegroundColor White
Write-Host "  预制: $cdnBase/harness-prefab-$ver.zip" -ForegroundColor White
Write-Host "禁止：把 zip 打进 TOA3-Setup（release_config_guard 已拦）" -ForegroundColor DarkGray
