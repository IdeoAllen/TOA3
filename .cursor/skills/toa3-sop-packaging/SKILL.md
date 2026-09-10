---
name: toa3-sop-packaging
description: >-
  TOA3 SOP-04 打包发版：build_windows、sync_portal_installer、运营台设当前版、版本对齐提交。
  Use when 打包、发版、Inno、安装包、APP_VERSION、release、Portal 上传.
---

# SOP-04 · 打包发版（Skill）

**正文**：`docs/规范/SOP-04-打包发版.md`  
**云侧**：`toa-cloud/docs/版本发布SOP.md`  
**标准**：STD-01 · A8 · B6

## 说「发版」必须做完

1. bump `APP_VERSION` → verify → `packaging/build_windows.py --clean --msi`  
2. **立刻上传**：`powershell -File ../toa-cloud/deploy/sync_portal_installer.ps1 -ReleaseVersion x.y.z`  
3. **停住**：请主理人在运营台「版本发布」→ 试链 → **设为当前版**  
4. 线上已切版后：`python scripts/sync_release_version.py --from-live --require-match --commit`（上传脚本常会自动做）

禁止只交付本地 `dist/` 路径、把上传甩给主理人。  
禁止打进 `data/user` / secrets / `license.json` / `app.dev.yml`。  
DMS 下载说明只建 draft，人审后部署（≠ TOA 安装包上传）。
