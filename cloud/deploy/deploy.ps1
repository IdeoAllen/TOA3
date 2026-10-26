# TOA Cloud 一键部署到生产（需 SSH 免密：ssh root@121.43.127.159）
# manifest / 当前版本：仅在运营台「版本发布」维护，本脚本不再 seed。
param(
  [string]$Server = "121.43.127.159",
  [string]$User = "root",
  [string]$AppDir = "/opt/toa-cloud",
  [string]$AdminUser = "admin",
  [string]$AdminPassword = "",
  [string]$ReleaseVersion = "",
  [switch]$SyncInstaller,
  [switch]$SkipDmsMigrate
)

$ErrorActionPreference = "Stop"
$DeployDir = $PSScriptRoot
$Root = Split-Path $DeployDir -Parent
$sshTarget = "${User}@${Server}"

if ($SyncInstaller -and -not $ReleaseVersion) {
  throw "SyncInstaller 需要 -ReleaseVersion x.y.z（例如 3.1.1）"
}
function New-RandomSecret {
  param([int]$Length = 48)
  $bytes = New-Object byte[] $Length
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', 'x').Replace('/', 'y').Substring(0, [Math]::Min($Length, 48))
}

function Invoke-RemoteBashScript {
  param([string]$Name, [string]$Body)
  $bodyLf = ($Body -replace "`r", "")
  $local = Join-Path $env:TEMP $Name
  [System.IO.File]::WriteAllText($local, $bodyLf, [System.Text.UTF8Encoding]::new($false))
  scp $local "${sshTarget}:/tmp/$Name"
  if ($LASTEXITCODE -ne 0) { throw "scp 远程脚本失败: $Name" }
  ssh $sshTarget ("bash /tmp/{0}" -f $Name)
  $ec = $LASTEXITCODE
  ssh $sshTarget ("rm -f /tmp/{0}" -f $Name) | Out-Null
  if ($ec -ne 0) { throw "远程脚本失败: $Name" }
}

Write-Host "==> 检查 SSH" -ForegroundColor Cyan
ssh -o BatchMode=yes -o ConnectTimeout=10 $sshTarget "echo ok" 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host "未配置 SSH 免密，请先: ssh-copy-id ${sshTarget}" -ForegroundColor Red
  exit 1
}

if (-not $AdminPassword) {
  $AdminPassword = New-RandomSecret -Length 16
  Write-Host "==> 已生成运营台初始密码（请妥善保存）: $AdminPassword" -ForegroundColor Yellow
}

$jwtSecret = New-RandomSecret -Length 48
$webhookSecret = New-RandomSecret -Length 32

Write-Host "==> 打包 toa-cloud" -ForegroundColor Cyan
$tarLocal = Join-Path $env:TEMP "toa-cloud-deploy.tar.gz"
if (Test-Path $tarLocal) { Remove-Item $tarLocal -Force }
Push-Location $Root
tar --exclude="./data" --exclude="venv" --exclude="__pycache__" --exclude="*.pyc" --exclude="*.db" --exclude=".env" --exclude=".gitignore" -czf $tarLocal .
Pop-Location
if (-not (Test-Path $tarLocal)) { throw "打包失败: $tarLocal" }

Write-Host "==> 上传代码包" -ForegroundColor Cyan
scp $tarLocal "${sshTarget}:/tmp/toa-cloud-deploy.tar.gz"
if ($LASTEXITCODE -ne 0) { throw "上传代码包失败" }

Write-Host "==> 上传 nginx / systemd" -ForegroundColor Cyan
scp (Join-Path $DeployDir "nginx-toa-service.yczh.tech.conf") "${sshTarget}:/tmp/nginx-toa-service.conf"
scp (Join-Path $DeployDir "toa-cloud.service") "${sshTarget}:/tmp/toa-cloud.service"
if ($LASTEXITCODE -ne 0) { throw "上传配置失败" }

$envBody = @"
TOA_CLOUD_ADMIN_USER=$AdminUser
TOA_CLOUD_ADMIN_PASSWORD=$AdminPassword
TOA_CLOUD_JWT_SECRET=$jwtSecret
TOA_CLOUD_WEBHOOK_SECRET=$webhookSecret
TOA_CLOUD_DATA_DIR=$AppDir/data
TOA_CLOUD_PUBLIC_BASE_URL=https://toa-service.yczh.tech
TOA_CLOUD_CORS_ORIGINS=https://toa-service.yczh.tech,https://www.yczh.tech
"@

$installScript = @'
set -euo pipefail
APP_DIR="__APP_DIR__"
mkdir -p "$APP_DIR/data"
if [ -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env" "$APP_DIR/.env.bak.$(date +%Y%m%d%H%M%S)"
fi
tar -xzf /tmp/toa-cloud-deploy.tar.gz -C "$APP_DIR"
if [ ! -f "$APP_DIR/.env" ]; then
  cat > "$APP_DIR/.env" << 'ENVEOF'
__ENV_BODY__
ENVEOF
  chmod 600 "$APP_DIR/.env"
else
  echo "保留已有 .env（未覆盖密码/JWT）"
fi
if [ ! -d "$APP_DIR/venv" ]; then
  python3.11 -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install -q -U pip
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
"$APP_DIR/venv/bin/python" "$APP_DIR/scripts/prune_product_plans.py" || true
install -m 644 /tmp/toa-cloud.service /etc/systemd/system/toa-cloud.service
systemctl daemon-reload
systemctl enable toa-cloud
systemctl restart toa-cloud
sleep 2
if ! curl -sf http://127.0.0.1:8090/api/health >/dev/null; then
  echo "FATAL: toa-cloud 本地 health 失败"
  journalctl -u toa-cloud -n 30 --no-pager || true
  exit 1
fi
echo "toa-cloud backend ok"
mkdir -p /var/www/certbot
CERT="/etc/letsencrypt/live/toa-service.yczh.tech/fullchain.pem"
if [ ! -f "$CERT" ]; then
  cat > /etc/nginx/conf.d/toa-service.conf << 'HTTPEOF'
server {
    listen 80;
    server_name toa-service.yczh.tech;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 200 'pending cert\n'; add_header Content-Type text/plain; }
}
HTTPEOF
  nginx -t
  systemctl reload nginx
  certbot certonly --webroot -w /var/www/certbot -d toa-service.yczh.tech \
    --non-interactive --agree-tos --register-unsafely-without-email || true
fi
install -m 644 /tmp/nginx-toa-service.conf /etc/nginx/conf.d/toa-service.conf
nginx -t
systemctl reload nginx
echo "nginx ok"
cd "$APP_DIR"
if [ "__SKIP_DMS__" = "0" ] && [ -f /var/lib/delivery-system/data.db ]; then
  "$APP_DIR/venv/bin/python" scripts/migrate_from_dms.py --dms-db /var/lib/delivery-system/data.db || true
fi
curl -sf http://127.0.0.1:8090/api/health
echo
'@

$installScript = $installScript.Replace("__APP_DIR__", $AppDir)
$installScript = $installScript.Replace("__ENV_BODY__", ($envBody -replace "`r", ""))
$installScript = $installScript.Replace("__SKIP_DMS__", $(if ($SkipDmsMigrate) { "1" } else { "0" }))

Write-Host "==> 远程安装 toa-cloud + nginx + cert" -ForegroundColor Cyan
Invoke-RemoteBashScript -Name "toa-cloud-install.sh" -Body $installScript

if ($SyncInstaller) {
  & (Join-Path $DeployDir "upload_installer.ps1") -ReleaseVersion $ReleaseVersion -Server $Server -User $User
}
Write-Host ""
Write-Host "==> 生产验收" -ForegroundColor Cyan
$verifyScript = @'
curl -sk https://toa-service.yczh.tech/api/health
echo
curl -sk "https://toa-service.yczh.tech/api/toa/releases/manifest?product=TOA3&channel=stable"
echo
'@
Invoke-RemoteBashScript -Name "toa-cloud-verify.sh" -Body $verifyScript

Write-Host ""
Write-Host "部署完成。" -ForegroundColor Green
Write-Host "  运营台: https://toa-service.yczh.tech/admin/" -ForegroundColor White
Write-Host "  发版 SOP: TOA3/docs/规范/SOP-04-打包发版.md（manifest 仅运营台维护）" -ForegroundColor DarkGray
Write-Host "  账号:   $AdminUser / $AdminPassword" -ForegroundColor White
Write-Host "  （若服务器已有 .env 则沿用旧密码，以 $AppDir/.env 为准）" -ForegroundColor DarkGray
Write-Host "  下载页: https://toa-service.yczh.tech/download/" -ForegroundColor White