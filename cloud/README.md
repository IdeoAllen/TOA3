# TOA 云服务（TOA3 子项目 `cloud/`）

TOA 桌面 **授权**、**功能包/假订单**、**版本发布**、**终端更新检查** 的后端 + 运营台 + 下载页（与 DMS 解耦）。

**生产域名**：`https://toa-service.yczh.tech` · 服务器目录 `/opt/toa-cloud`

## TOA3 子项目布局

| 子项目 | 目录 | 说明 |
|--------|------|------|
| 桌面客户端 | 仓库根（`app/` `services/` `modules/` …） | PySide6；打包 `packaging/` |
| 云后端 | `cloud/backend/` | FastAPI，`127.0.0.1:8090` |
| 运营台 | `cloud/admin/` | `/admin/` 静态页，后端挂载 |
| 下载页 + 安装包 | `cloud/download/` | `/download/`（`/opt/toa-cloud/download/`） |
| 部署 | `cloud/deploy/` | `deploy.ps1` 部署云服务；`upload_installer.ps1` 发版上传 |

规范、发版流程只认 TOA3 `docs/规范/`（发版：`SOP-04-打包发版.md`）；本目录不另立流程文档。

## 下载地址（唯一）

| 项 | 地址 | 真相源 |
|----|------|--------|
| 下载页 | `https://toa-service.yczh.tech/download/` | `backend/config.py` `DOWNLOAD_BASE_URL` |
| 安装包直链 | `https://toa-service.yczh.tech/download/TOA3-Setup-v{ver}.exe` | `config.installer_url()` |
| 运营台读取 | `GET /api/toa/releases/download-config` | 运营台 / 脚本勿写死 |

旧地址 `/downloads/`（含 `www.yczh.tech/downloads/` 301 链）→ 301 到 `/download/`。

## 能力

| 模块 | 公开 API | 运营台 |
|------|----------|--------|
| 授权 | `POST /api/toa-license/*` | 授权管理 |
| 功能包 | `GET /api/toa/packs` | 功能包规划 |
| 假订单 | `POST /api/toa/orders` | 假订单 → 模拟付款 → 发卡 |
| 支付回调 | `POST /api/toa/payments/webhook/{channel}` | 微信/支付宝占位 |
| 续费拉码 | `POST /api/toa-license/upgrade` | 终端同步已付订单 |
| 版本 | `GET /api/toa/releases/manifest` | 版本发布（升级包） |

TOA3 配置：

```yaml
license:
  service_url: https://toa-service.yczh.tech/api/toa-license
update:
  manifest_url: https://toa-service.yczh.tech/api/toa/releases/manifest?product=TOA3&channel=stable
  download_page: https://toa-service.yczh.tech/download/
```

## 功能包与假订单（无真实支付）

- **基础版** `local_free`：单机免费层，不卖，仅规划展示
- **收费包** `starter` / `professional` / `enterprise` 等：见 `config/feature_packs.yml`
- **参考价** `config/commerce.yml` → `pack_prices_yuan`
- **流程**：终端/运营台创建订单 → **模拟付款或 webhook** → 同手机号 **自动续费延长** → 签发/更新 TOA2 码

### 支付 Webhook（占位）

```http
POST /api/toa/payments/webhook/wechat
X-TOA-Webhook-Secret: <TOA_CLOUD_WEBHOOK_SECRET>

{
  "event": "payment.success",
  "order_no": "TOA20260827ABC",
  "phone": "13800138000",
  "transaction_id": "wx_unique_id"
}
```

本地未配置 secret 时可无签名调用 `webhook/mock` 联调。生产请设 `TOA_CLOUD_WEBHOOK_SECRET`。

### 同手机号续费

第二次购买同一手机号时，到期日从 `max(今天, 原到期日) + 购买天数` 累加，并换发新码（**保留机器绑定**）。

终端拉码：`POST /api/toa-license/upgrade` `{ "order_no", "phone", "machine_id" }`

同步功能包（TOA3 改 pack 后执行）：

```powershell
.\scripts\sync_feature_packs.ps1
```

## 本地启动

```powershell
cd TOA3\cloud
pip install -r requirements.txt
.\scripts\run_dev.ps1
```

- 运营台：http://127.0.0.1:8090/admin/
- 冒烟：`python scripts/smoke_commerce.py`

## 部署

```powershell
cd TOA3\cloud\deploy
powershell -ExecutionPolicy Bypass -File .\deploy.ps1
```

- Nginx：`deploy/nginx-toa-service.yczh.tech.conf` → `/etc/nginx/conf.d/toa-service.conf`
- 后端：`/opt/toa-cloud`，systemd 单元 `toa-cloud.service`，监听 `127.0.0.1:8090`
- 代码包**不含** `data/`、`.env`、`*.db`（生产数据只在服务器，禁止本地覆盖）
- 首次部署自动申请 `toa-service.yczh.tech` 证书
- 发版上传安装包：`powershell -File cloud\deploy\upload_installer.ps1 -ReleaseVersion x.y.z`

## 从 DMS 迁移台账

```powershell
python scripts/migrate_from_dms.py --dms-db "DMS\backend\data.db"
```

架构：`docs/architecture/ARCH-04-授权与单机联网.md`
