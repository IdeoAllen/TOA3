#!/usr/bin/env bash
# 仅更新 /opt/toa-cloud/backend（不动 venv/.env 已有项/data），先备份代码与库，失败自动回滚。
# 用法：scp backend.tgz 到 /tmp/toa-backend.tgz 后执行本脚本
set -euo pipefail
APP_DIR=/opt/toa-cloud
TS=$(date +%Y%m%d%H%M%S)
BK="$APP_DIR/backups/$TS"
mkdir -p "$BK"
cp -a "$APP_DIR/backend" "$BK/backend"
for f in "$APP_DIR"/data/*.db; do [ -f "$f" ] && sqlite3 "$f" ".backup '$BK/$(basename "$f")'" 2>/dev/null || cp -a "$f" "$BK/"; done
echo "backup -> $BK"

# 巨龙服务间密钥：TOA 云与巨龙正式环境共用，只生成一次，不输出
if ! grep -q '^JULONG_INTERNAL_SECRET=' "$APP_DIR/.env"; then
  SECRET=$(openssl rand -hex 32)
  printf '\nJULONG_INTERNAL_SECRET=%s\n' "$SECRET" >> "$APP_DIR/.env"
  echo "secret generated"
fi
SECRET=$(grep '^JULONG_INTERNAL_SECRET=' "$APP_DIR/.env" | tail -1 | cut -d= -f2-)
JL_ENV=/opt/julong-platform/.env.local
if [ -f "$JL_ENV" ] && ! grep -q '^JULONG_INTERNAL_SECRET=' "$JL_ENV"; then
  cp "$JL_ENV" "$JL_ENV.bak-onecode-$TS"
  printf '\nJULONG_INTERNAL_SECRET=%s\nTOA_CLOUD_INTERNAL_URL=http://127.0.0.1:8090\n' "$SECRET" >> "$JL_ENV"
  echo "julong prod env updated (backup $JL_ENV.bak-onecode-$TS)"
fi

rm -rf /tmp/toa-backend-new && mkdir -p /tmp/toa-backend-new
tar -xzf /tmp/toa-backend.tgz -C /tmp/toa-backend-new
rsync -a --delete --exclude '__pycache__' /tmp/toa-backend-new/ "$APP_DIR/backend/"
systemctl restart toa-cloud
ok=0
for i in $(seq 1 15); do sleep 1; if curl -sf http://127.0.0.1:8090/api/health >/dev/null; then ok=1; break; fi; done
if [ "$ok" != 1 ]; then
  echo "FATAL: health 失败，回滚"
  journalctl -u toa-cloud -n 30 --no-pager || true
  rsync -a --delete "$BK/backend/" "$APP_DIR/backend/"
  systemctl restart toa-cloud
  exit 1
fi
echo "health ok"

# 冒烟：外部请求被拒、无密钥被拒、校验接口可用
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'X-Real-IP: 1.1.1.1' -H "X-Internal-Secret: $SECRET" -H 'Content-Type: application/json' -d '{"license_key":"x"}' http://127.0.0.1:8090/api/toa-license/platform-verify)
echo "proxied -> $code (expect 403)"
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{"license_key":"x"}' http://127.0.0.1:8090/api/toa-license/platform-verify)
echo "no-secret -> $code (expect 401)"
curl -s -X POST -H "X-Internal-Secret: $SECRET" -H 'Content-Type: application/json' -d '{"license_key":"x"}' http://127.0.0.1:8090/api/toa-license/platform-verify; echo
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST https://toa-service.yczh.tech/api/toa-license/platform-verify -H "X-Internal-Secret: $SECRET" -H 'Content-Type: application/json' -d '{"license_key":"x"}')
echo "public -> $code (expect 403)"
sqlite3 "$APP_DIR/data/toa_cloud.db" "select count(*) from pragma_table_info('toa_licenses') where name='platform_user_id';" 2>/dev/null | sed 's/^/platform_user_id column: /' || true
rm -rf /tmp/toa-backend-new /tmp/toa-backend.tgz
