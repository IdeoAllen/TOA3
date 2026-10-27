# 上传 TOA3 安装包 + 下载页到 toa-service（发版 SOP-04 第 2 步）
# 唯一入口：https://toa-service.yczh.tech/download/（服务器 /opt/toa-cloud/download/）
#   下载页 index.html 读运营台 manifest；安装包 TOA3-Setup-v{ver}.exe 与之同目录。
param(
  [Parameter(Mandatory = $true)]
  [string]$ReleaseVersion,
  [string]$Server = "121.43.127.159",
  [string]$User = "root",
  [string]$DownloadDir = "/opt/toa-cloud/download",
  [string]$PublicBaseUrl = "https://toa-service.yczh.tech"
)

$ErrorActionPreference = "Stop"
$CloudRoot = Split-Path $PSScriptRoot -Parent
$Toa3Root = Split-Path $CloudRoot -Parent
$ver = $ReleaseVersion.Trim().TrimStart('v', 'V')
$fileName = "TOA3-Setup-v$ver.exe"
$local = Join-Path $Toa3Root "packaging\dist\$fileName"
if (-not (Test-Path $local)) {
  throw "未找到 $local（请先 python packaging/build_windows.py --clean --msi）"
}
$pageLocal = Join-Path $CloudRoot "download\index.html"
$downloadBase = "$($PublicBaseUrl.TrimEnd('/'))/download/"
$expectedUrl = "$downloadBase$fileName"

$sshTarget = "${User}@${Server}"
ssh $sshTarget "mkdir -p $DownloadDir"
if ($LASTEXITCODE -ne 0) { throw "SSH 失败" }

Write-Host "==> 上传 $fileName ($('{0:N1}' -f ((Get-Item $local).Length / 1MB)) MB)" -ForegroundColor Cyan
scp $local "${sshTarget}:${DownloadDir}/$fileName"
if ($LASTEXITCODE -ne 0) { throw "上传安装包失败" }
foreach ($f in Get-ChildItem (Split-Path $pageLocal -Parent) -File) {
  scp $f.FullName "${sshTarget}:${DownloadDir}/$($f.Name)"
  if ($LASTEXITCODE -ne 0) { throw "上传下载页文件失败: $($f.Name)" }
}

Write-Host "==> 试链 $expectedUrl" -ForegroundColor Cyan
$head = Invoke-WebRequest -Uri $expectedUrl -Method Head -UseBasicParsing
$remoteLen = [int64]($head.Headers["Content-Length"] | Select-Object -First 1)
if ($head.StatusCode -ne 200 -or $remoteLen -ne (Get-Item $local).Length) {
  throw "直链校验失败：HTTP $($head.StatusCode)，远端 $remoteLen 字节，本地 $((Get-Item $local).Length) 字节"
}
Write-Host "直链 200，大小一致。" -ForegroundColor Green

Write-Host "==> 校验运营台 manifest" -ForegroundColor Cyan
try {
  $manifestUrl = "$($PublicBaseUrl.TrimEnd('/'))/api/toa/releases/manifest?product=TOA3&channel=stable&format=json"
  $m = Invoke-RestMethod -Uri $manifestUrl -Headers @{ Accept = "application/json" }
  $currentVer = [string]$m.latest_version
  if (-not $currentVer) { $currentVer = [string]$m.version }
  if ($currentVer -ne $ver) {
    Write-Host "运营台当前版 v$currentVer；本次 v$ver 待预登记 + 主理人「设为当前」。" -ForegroundColor Yellow
  } elseif ([string]$m.download_url -ne $expectedUrl) {
    Write-Warning "运营台 v$ver 的 download_url 不是 $expectedUrl（当前: $($m.download_url)）"
  } else {
    Write-Host "manifest 与上传包一致。" -ForegroundColor Green
  }
} catch {
  Write-Warning "无法读取 manifest（不影响上传）: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "完成。下一步：python cloud/scripts/prepare_ops_release.py --version $ver --notes-file …（预登记）→ 主理人只点「设为当前」" -ForegroundColor Green
Write-Host "  下载页:     $downloadBase" -ForegroundColor White
Write-Host "  安装包直链: $expectedUrl" -ForegroundColor White
Write-Host "  运营台:     $($PublicBaseUrl.TrimEnd('/'))/admin/" -ForegroundColor White
Write-Host "  切版后:     python scripts/sync_release_version.py --from-live --require-match --commit" -ForegroundColor Yellow
