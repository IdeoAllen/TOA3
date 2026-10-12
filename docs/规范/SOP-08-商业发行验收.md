# SOP-08 · 商业发行验收

> **编号**：SOP-08 · **Skill**：`toa3-sop-commercial-release`  
> **依据**：STD-01 · **A10.4** · A8 · A9 · B6 · B9 · SOP-04 §1.1 · ARCH-04 · PROD-01/02  
> **边界**：本 SOP = **称可商用 / 设当前版前** 的严格验收与整改作业；日常 Setup 五步仍走 SOP-04。

## 1. 目的

以软件工程 + 产品合格双尺子验收 TOA3，输出 **通过 / 有条件通过 / 不通过** 与分阶整改；禁止未过 A10.4 称「可商用当前版」。

## 2. 验收尺子（必须同时看）

| 维度 | 通过条件 | 真相源 |
|------|----------|--------|
| **A10.4 硬闸** | ① `verify_all` 绿 ② `show:true` 无进页即崩/丢数据级 gaps ③ 发版说明诚实 ④ 授权/SKU 隔离 ⑤ 密钥未入包 ⑥ 商用冒烟勾完 | STD-01 A10.4 · SOP-04 |
| **日用可售** | Wave★ 点验清 gaps → `done`；对外话术与灯色一致 | PROD-01 §0.5 · `migration_manifest` |
| **商务叙事** | 不承诺未点验能力「不能比同类差」 | PROD-02 · `product.yml` |
| **授权** | 默认 `toa-service`；生产禁 DMS fallback；激活云可达 | ARCH-04 · `app.release.yml` |

**综合**：A10.4 未过 → 禁止设当前版 / 称可商用。A10.4 过但 Wave★ 仍 mvp → 仅可「预发 / 培训工具链可用」，禁止「办公八件套已完成」。

## 3. Agent 作业流程（说「商业验收 / 正式发行」必做）

### 3.1 摸底（只读）

1. 读 `app/version.py`、`config/update_manifest.yml`、线上 stable manifest  
2. 读 `config/migration_manifest.yml` + `config/app.yml` `show`：列出 Wave★ / `show:true` 且非 done  
3. 读 OPS-01 发版状态、CDN/证书遗留  
4. 输出验收表（工程 / 产品 / 商务 / 授权 / 综合裁定）

### 3.2 P0 · 发行硬闸（挡设当前版）

| # | 动作 | 判据 / 命令 |
|---|------|-------------|
| 1 | CDN/TLS + 门禁 | `python scripts/verify_all.py` 全绿（含 `verify_license_gate`） |
| 2 | 商用冒烟自动项 | `python scripts/commercial_smoke_checklist.py` |
| 3 | 商用冒烟人工 1–5 | 干净机安装 / 升级不丢数据 / show 进页 / 热键非阻塞 / 授权隔离（**主理人勾**） |
| 4 | 侧栏收口 | 非点验凑数 mvp → `show:false`；Wave★/点验池可留；Wave F 未点验宜暂隐（PROD-01 §0.6 D） |
| 5 | 诚实发版说明 | SOP-04 §2.1；`update_manifest.release_notes` 写 Wave★/激活需网/Harness 限制 |
| 6 | 生产日志 | `app.release.yml`：`log_level`≥INFO、`enable_console_log: false` |
| 7 | 授权生产面 | `allow_dms_fallback: false`；`dms_base_url: ""`；`skip_login: false` |
| 8 | 云健康 | `toa-service` `/api/health` + stable manifest 可达 |
| 9 | 切版闭环 | 主理人运营台「设为当前」→ `python scripts/sync_release_version.py --from-live --require-match --commit` |

### 3.3 P1 · 日用可售（挡「办公套件」话术）

1. **主理人点验** Wave★ → 清 gaps → `done`（禁止 Agent 假清）  
2. Wave F 点验后恢复 `show`，或继续隐  
3. `verify_license_gate` 保持进 `verify_all`  
4. 回写 `migration_manifest` · OPS-01；对齐 PROD-02 / `product.yml`

### 3.4 P2 · 工程债（不挡软发）

1. 消 `services`→`modules` 运行时依赖  
2. ARCH-04 §9 商业参数与 `feature_packs` / release 一致  
3. Harness CDN 与内核钉扎 + 干净机点验  
4. CI 子集（`.github/workflows/verify.yml`）维持绿  
5. OPS-01 清过时勾选（旧版本号 / WIP 上限等）

## 4. 禁止

- 未过 A10.4 称可商用 / 设当前版  
- 有 gaps 标 `done`；Wave★ 未点验写「对标头部且更稳」  
- 生产 `skip_login` / `dev_grant_all` / DMS 静默 fallback  
- 把 `license.json` / secrets / `app.dev.yml` / `harness-*.zip` 打进 Setup  
- 另建平行「发行方案.md」；进度只写 OPS-01  

## 5. 回写

会话结束：OPS-01 记一行（验收结论 + 未勾人工项）。规范意见改本 SOP / STD-01 A10.4 / PROD-02（SOP-07）。

## 6. 与 SOP-04 分工

| 场景 | 走 |
|------|-----|
| 升版 · 打包 · 上传 · 预登记 · 设当前 · 对齐提交 | **SOP-04** / `toa3-sop-packaging` |
| 称可商用前严格验收 · 侧栏/话术/授权硬闸 · 分阶整改 | **本 SOP** / `toa3-sop-commercial-release` |
| 单模块点验清 gaps | SOP-03 / `toa3-sop-module-accept` |
