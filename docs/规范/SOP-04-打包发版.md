# SOP-04 · 打包发版

> **编号**：SOP-04 · **Skill**：`toa3-sop-packaging`  
> **依据**：STD-01 · A8 · B6

## 1. 目的

产出可安装的 Windows 包，不含本机密钥与用户数据。

## 2. 步骤

| 步 | 动作 | 判据 |
|----|------|------|
| 1 | 确认 `app/version.py` → `APP_VERSION` | 与发版说明一致 |
| 2 | 使用 `packaging/shipped_config/*` 干净配置 | 无本机脏 harness/secrets |
| 3 | `python scripts/verify_all.py`（或 mvp + 护栏） | 退出码 0 |
| 4 | `python packaging/build_windows.py` + Inno | `dist/` 有 Setup |
| 5 | `packaging/release_config_guard.py` / secrets 审计 | 通过 |
| 6 | 需要时 `scripts/sync_release_version.py` | 版本对齐 |
| 7 | DMS 仅改下载说明时：只建 **draft**，人审后再部署 | 遵守 `dms-release-deploy.mdc` |

## 3. 禁止打进包

`data/user` · `license.json` · `app.dev.yml` · secrets · 本机日志 · `skip_login`
