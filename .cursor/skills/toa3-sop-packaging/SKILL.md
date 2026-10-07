---
name: toa3-sop-packaging
description: >-
  TOA3 SOP-04 打包发版：build_windows、sync_portal_installer、运营台设当前版、版本对齐提交；
  以及 Harness 双包 CDN（build_harness_prefab、sync_portal_harness、sync_harness_bundles）。
  Use when 打包、发版、Inno、安装包、APP_VERSION、release、Portal 上传、Harness CDN、预制包.
---

# SOP-04 · 打包发版（Skill）

**正文**：`docs/规范/SOP-04-打包发版.md`  
**云侧**：`toa-cloud/docs/版本发布SOP.md`  
**标准**：STD-01 · A8 · B6  
**Harness 生命周期**：`docs/architecture/ARCH-10-Harness全生命周期.md` §4.4

## 说「发版」必须做完（TOA Setup）

**分工（主理人裁定 2026-09-22）**：Agent 备齐版本号/说明/直链/运营台预登记；**主理人只点「设为当前」**；切版后 Agent 立刻对齐提交。

1. bump `APP_VERSION` → 写好 `release_notes`（SOP-04 §2.1 模板）→ `verify_all` → `packaging/build_windows.py --clean --msi`  
2. **立刻上传**：`powershell -File ../toa-cloud/deploy/sync_portal_installer.ps1 -ReleaseVersion x.y.z`  
3. **Agent 预登记运营台**（`is_current=false`，说明/直链已填）：  
   `python ../toa-cloud/scripts/prepare_ops_release.py --version x.y.z --notes "……"`  
4. **停住**：请主理人只点「设为当前」（禁止让主理人再填说明）  
5. **主理人确认已切版后立刻提交**：  
   `python scripts/sync_release_version.py --from-live --require-match --commit`  
   回报 commit hash；失败不得当发版完成。

禁止只交付本地 `dist/` 路径、把上传/填说明甩给主理人。  
禁止打进 `data/user` / secrets / `license.json` / `app.dev.yml` / **`harness-*.zip`**。  
DMS 下载说明只建 draft，人审后部署（≠ TOA 安装包上传）。

## 发版说明（必填 · 运营台粘贴）

见 SOP-04 §2.1。`release_notes` + 运营台版本说明须同义；全局键变更点名 ARCH-11 id。  
版本对齐清单：SOP-04 §2.2。线上未切版前禁止 `--from-live` 回写旧号。

全局壳验证：`python scripts/verify_global_shell.py`（已挂 `verify_all`）。

## 说「发 Harness 包 / 上 CDN」必须做完（与 Setup 分离）

1. 构包：`python scripts/build_harness_prefab.py --source <runtime> --out packaging/dist/harness --version {ver}`  
2. **立刻上传**：`powershell -File ../toa-cloud/deploy/sync_portal_harness.ps1 -BundleVersion {ver}`  
3. **停住**：请主理人确认 **切配置**（切 yml = 用户立刻下新包）  
4. 确认后：`python scripts/sync_harness_bundles.py --from-dist --version {ver} --apply --verify-cdn`（可选 `--commit`）

禁止把 Harness zip 打进 Setup；禁止未确认就改 `config/harness.yml` / shipped。
