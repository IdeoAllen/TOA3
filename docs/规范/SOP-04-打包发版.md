# SOP-04 · 打包发版

> **编号**：SOP-04 · **Skill**：`toa3-sop-packaging`  
> **依据**：STD-01 · A8 · **A10.4（商用可交付）** · B6 · **B9（统筹发版）**  
> **云侧**：TOA3 子项目 `cloud/`（后端 + 运营台 + 下载页 + 部署脚本，见 `cloud/README.md`）；发版流程只认本 SOP

## 1. 目的

产出可安装的 Windows 包并上传到 `toa-service.yczh.tech/download/`；不含本机密钥与用户数据。  
**对外称可商用 / 设为当前版前**：必须满足 STD-01 **A10.4**（含商用冒烟）与 **A9.4**（升显权）。并行分轨合入后由 **统筹** 跑门禁再发版（B9）。重大门禁变更须过专家组（B10）。

## 1.1 商用冒烟（设当前版前 · 统筹勾选）

自动可检项（护栏/授权/本地版本/migration）：`python scripts/commercial_smoke_checklist.py`  
人工项仍须统筹勾选下表 1–5（第 6 项已含在自动脚本）。

| # | 项 | 判据 |
|---|-----|------|
| 1 | 安装包冒烟 | 干净机装 Setup → 首启 → 顶栏三级导航 → 退出/再开不崩 |
| 2 | 升级路径 | 有旧版数据目录时升级 → Wave★ 核心页可进、数据不丢 |
| 3 | show 进页抽检 | 本版菜单每一 `show: true` 项进页不崩；有落盘则保存/再开一轮 |
| 4 | 热键/召唤非阻塞 | 截图/双 Ctrl 等不触发同步长联网卡死 |
| 5 | edition/授权隔离 | 配置不串；未授权模块不可用且提示诚实 |
| 6 | 敏感面 | `release_config_guard` 绿；diff 无 secrets/IMAP 明文/样例密钥入包 |

## 2. 发版五步（主理人裁定 · 说「发版」必须做完 1–3）

**分工（2026-09-22）**：Agent 备齐一切；**主理人只点「设为当前」**；切版后 Agent 对齐提交。

| 步 | 动作 | 判据 |
|----|------|------|
| 1 | 升 `APP_VERSION` → 写好更新说明 → verify → `python packaging/build_windows.py --clean --msi` | `packaging/dist/TOA3-Setup-v{ver}.exe` |
| 2 | **上传安装包**（Agent 必做） | `powershell -File cloud/deploy/upload_installer.ps1 -ReleaseVersion {ver}` → exe + 下载页传到 `/opt/toa-cloud/download/`，脚本 HEAD 试链 200 + 大小一致 |
| 3 | **Agent 预登记运营台**（说明+直链已填，`is_current=false`） | `python cloud/scripts/prepare_ops_release.py --version {ver} --notes "…"` → 列表可见该版 |
| 4 | **主理人只点「设为当前」** | 运营台列表该行点一次即可；禁止再让主理人粘贴说明 |
| 5 | 对齐并提交 | 切版后 Agent：`python scripts/sync_release_version.py --from-live --require-match --commit` 并回报 hash |
| 6 | 验收 | 桌面「检查更新」+ https://toa-service.yczh.tech/download/ 与 `APP_VERSION` 同号 |

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

下载地址约定（主理人 2026-10-26 裁定 · **唯一入口**）：

| 项 | 地址 |
|----|------|
| 下载页（`download_page`） | `https://toa-service.yczh.tech/download/` |
| 安装包直链（`download_url`） | `https://toa-service.yczh.tech/download/TOA3-Setup-v{ver}.exe` |
| Harness 双包 | `https://toa-service.yczh.tech/download/harness-{official,prefab}-{ver}.zip` |

- 服务器目录 `/opt/toa-cloud/download/`（下载页 `cloud/download/index.html` 读 manifest，与安装包同目录）；nginx 见 `cloud/deploy/nginx-toa-service.yczh.tech.conf`。
- 真相源：`cloud/backend/config.py`（`DOWNLOAD_BASE_URL` / `installer_url()`）；运营台读 `GET /api/toa/releases/download-config`；客户端 `config/app*.yml` `update.download_page` 同值。**禁止**在别处另写下载域名。
- 旧地址 `toa-service…/downloads/`、`www.yczh.tech/downloads/` 一律 301 到 `/download/`（历史包已硬链接过来）；不得再作为新登记地址。

### 2.1 发版说明（运营台 / update_manifest 必填）

发版前把下列字段写清；**禁止**只写「修复若干问题」。

| 字段 | 写什么 | 例子 |
|------|--------|------|
| `APP_VERSION` | 仅改 `app/version.py` | `3.1.18` |
| `release_notes` | 用户能懂的变更点 · 分号或顿号分隔 · ≤120 字优先 | `双击Ctrl唤起稳定；拖入开桌面可关；热键开发版优先` |
| 运营台「版本说明」 | 与 `release_notes` **同义扩写**（可分段） | 见模板 |
| 全局能力变更 | 改了哪条 `GLOBAL_FEATURES` id | 见 ARCH-11 |

**运营台粘贴模板**（步 3 前填好）：

```text
【版本】v{ver}
【本版要点】
1. …
2. …
3. …
【全局介入/热键】（无则写「无」）
- 双击 Ctrl / 截图 / 拖入桌面 / F11 / 退出：…
【已知限制】
- …
【验收】安装包直链试链通过；检查更新可见本号
```

本地回退同步：`config/update_manifest.yml` 的 `version` / `download_url` / `release_notes` 须与 `APP_VERSION` 同号（打包脚本 `--from-app` 会写；切版后 `--from-live` 再钉）。

### 2.2 版本对齐清单（防漂移）

发版前后逐项打勾：

| # | 检查项 | 命令 / 位置 |
|---|--------|-------------|
| 1 | 代码版本 | `app/version.py` → `APP_VERSION` |
| 2 | 打包产物文件名 | `packaging/dist/TOA3-Setup-v{ver}.exe` |
| 3 | 安装包直链 200 | `https://toa-service.yczh.tech/download/TOA3-Setup-v{ver}.exe` |
| 4 | 运营台当前版 = `{ver}` | 主理人勾选后才算 |
| 5 | 本地 manifest | `config/update_manifest.yml` `version` / `download_url` |
| 6 | 全局壳门禁 | `python scripts/verify_global_shell.py`（`verify_all` 已挂） |
| 7 | 对齐提交 | 线上已切版后：`python scripts/sync_release_version.py --from-live --require-match --commit` |

**硬规则**：线上 stable ≠ `APP_VERSION` 时，**禁止**用 `--from-live` 把本地打回旧号；先切运营台，再 sync。  
`--from-live --require-match` 须先核对版本再写文件（不一致则失败且不改本地）。

全局热键 / 拖入 / 全屏档案：`docs/architecture/ARCH-11-全局介入与热键.md` · `services/global_shell_features.py`。

## 3. 禁止打进包

`data/user` · `license.json` · `app.dev.yml` · secrets · 本机日志 · `skip_login`

## 4. 与 DMS 的边界

- TOA 安装包走 Portal + TOA 运营台；**不要**把「发版」理解成 DMS `deploy.ps1`。
- 仅当改 DMS 站上的下载说明文案时：只建 **draft**，人审后再部署（`dms-release-deploy.mdc`）。

## 5. Harness 双包 CDN 发版（与 Setup **分离**）

> **硬约束**：`harness-*.zip` **永不**打进 `TOA3-Setup`（体积大；`release_config_guard` + gitignore）。  
> 体验契约：ARCH-10 §4.4。说「发 Harness 包 / 上 CDN」走本节约，**≠** SOP-04 §2 的 Setup 五步。

### 五步（对标 Setup：上传必做 · 切配置等人）

| 步 | 动作 | 判据 |
|----|------|------|
| 1 | 已知可用机构包 | `python scripts/build_harness_prefab.py --source <runtime> --out packaging/dist/harness --version {ver}` → 双 zip + `.sha256` + `harness-bundles-{ver}.json` |
| 2 | **上传 CDN**（Agent 必做，禁止只丢本地路径） | `powershell -File cloud/deploy/upload_harness.ps1 -BundleVersion {ver}` → 两直链 HEAD 200 |
| 3 | **主理人确认「切配置」**（人工闸门） | 切 yml = 用户立刻下到新包；未确认前**禁止**改 `harness.yml` |
| 4 | 回写钉扎并验收 | `python scripts/sync_harness_bundles.py --from-dist --version {ver} --apply --verify-cdn`（可选 `--commit`） |
| 5 | 门禁 | `python scripts/verify_harness_cdn.py` 绿；Setup 体积未因 zip 暴涨 |

直链约定：

- `https://toa-service.yczh.tech/download/harness-official-{ver}.zip`
- `https://toa-service.yczh.tech/download/harness-prefab-{ver}.zip`

配置双写（须一致）：`config/harness.yml` · `packaging/shipped_config/harness.yml`  
字段：`official_bundle_*` / `prefab_bundle_*`（url / sha256 / version / size_hint_mb）。

仅换 CDN 钉扎、Host 代码未变 → **不必**重打 TOA Setup；已装用户下次进「编码智能体」见页顶弱提示「更新环境」（确认才下）。Host 也变 → 再走 §2 Setup 发版。
