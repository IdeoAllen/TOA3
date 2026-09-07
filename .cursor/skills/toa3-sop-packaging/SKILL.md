---
name: toa3-sop-packaging
description: >-
  TOA3 SOP-04 打包发版：build_windows、shipped_config、密钥护栏。
  Use when 打包、发版、Inno、安装包、APP_VERSION、release.
---

# SOP-04 · 打包发版（Skill）

**正文**：`docs/规范/SOP-04-打包发版.md`  
**标准**：STD-01 · A8 · B6

确认版本 → shipped_config → verify → `packaging/build_windows.py` → 护栏 → 可选 sync_release_version。  
禁止打进 `data/user` / secrets / `license.json` / `app.dev.yml`。  
DMS 下载说明只建 draft，人审后部署。
