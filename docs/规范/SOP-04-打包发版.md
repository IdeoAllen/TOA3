# SOP-04 · 打包发版

> **编号**：SOP-04 · **Skill**：`toa3-sop-packaging`  
> **依据**：STD-01 · A8 · B6  
> **云侧细则**：`toa-cloud/docs/版本发布SOP.md`（五步真相源）

## 1. 目的

产出可安装的 Windows 包并上到 Portal；不含本机密钥与用户数据。

## 2. 发版五步（主理人裁定 · 说「发版」必须做完 1–2）

| 步 | 动作 | 判据 |
|----|------|------|
| 1 | 升 `APP_VERSION` → verify → `python packaging/build_windows.py --clean --msi` | `packaging/dist/TOA3-Setup-v{ver}.exe` |
| 2 | **上传安装包**（Agent 必做，禁止只丢本地路径） | `powershell -File ../toa-cloud/deploy/sync_portal_installer.ps1 -ReleaseVersion {ver}` → 直链 200 |
| 3 | **运营台设为当前版**（仅主理人） | https://toa-service.yczh.tech/admin/ → 版本发布 → 试链 → 勾选「设为当前版」 |
| 4 | 对齐并提交 | 上传脚本在线上已切版时会自动 commit；否则：`python scripts/sync_release_version.py --from-live --require-match --commit` |
| 5 | 验收 | 桌面「检查更新」+ https://www.yczh.tech/downloads/ 与 `APP_VERSION` 同号 |

### 本地打包门禁（步 1 内）

| 子步 | 动作 |
|------|------|
| a | 使用 `packaging/shipped_config/*`；`python scripts/verify_all.py`（或 mvp + 护栏） |
| b | `packaging/release_config_guard.py` / secrets 审计通过 |
| c | 打包成功会按 `APP_VERSION` 写 `config/update_manifest.yml`（`--from-app`） |

### 版本统一（禁止漂移）

| 环境 | 真相源 |
|------|--------|
| 代码 / 安装包 | `app/version.py` → `APP_VERSION` |
| 生产 stable | 运营台 manifest |
| 本机离线回退 | `config/update_manifest.yml`（须与 stable 同号） |

直链约定：`https://www.yczh.tech/downloads/TOA3-Setup-v{ver}.exe`

## 3. 禁止打进包

`data/user` · `license.json` · `app.dev.yml` · secrets · 本机日志 · `skip_login`

## 4. 与 DMS 的边界

- TOA 安装包走 Portal + TOA 运营台；**不要**把「发版」理解成 DMS `deploy.ps1`。
- 仅当改 DMS 站上的下载说明文案时：只建 **draft**，人审后再部署（`dms-release-deploy.mdc`）。
