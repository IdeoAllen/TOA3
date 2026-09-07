# 15 · WCS 退役与平台收敛规划

> **状态**：主理人裁定 · 远期停 WCS  
> **版本**：v1 · 2026-08  
> **适用范围**：Portal · DMS · TOA · WCS（归档）  
> **关联**：`10-必备能力与Portal评估.md` · `toa3-portal-integration.mdc`

---

## 1. 目标态（WCS 停服后）

### 1.1 平台组成

| 组件 | 定位 | 必装 |
|------|------|------|
| **Portal** | 静态入口：产品说明、TOA 下载、链到 DMS、全站手册 | 是（轻量站点） |
| **DMS** | 交付操作系统：班级真相源、Web 协作、企微触达、TOA 授权台账 | 是 |
| **TOA** | 桌面效率工具：课前生成、本机菜单、授权码登录 | 是（运营侧） |
| **WCS** | ~~企微智能客服~~ | **否（退役）** |

### 1.2 治理边界（收敛后仍保持分治）

| 领域 | 主数据 / 真相源 | 说明 |
|------|-----------------|------|
| DMS Web 账号 | DMS `users` + RBAC | 助教/运营/财务 Web 登录 |
| DMS Web 菜单 | DMS 角色菜单树 | 与 TOA 无关 |
| TOA 桌面授权 | DMS `toa_licenses` + 本机 `license.json` | 发码在 DMS，激活在桌面 |
| TOA 侧栏菜单 | TOA `config/app.yml` + `migration_manifest` | 不发版不改；**不经 Portal/DMS 远程下发** |
| 企微绑群 | DMS `class_workgroups` | 已从 WCS 收回 |
| 群事件通知 | DMS `workgroup_notify` + `aibot_ws_service` | 已从 WCS 收回 |

**Portal 永不承担**：统一账号、统一菜单、业务 API。

### 1.3 交付主链（修订蓝图）

```text
课前准备（TOA 本地） → 建班交付（DMS Web） → 企微触达（DMS 直连企微）
                              ↑
                    TOA 生成物人工上传，不同步
```

客户查进度、FAQ、人工客服：**不再依赖独立 WCS**；改为「群内需知由 DMS 事件/定时推送 + 运营人工答复」（见 §4）。

---

## 2. 现状：WCS 能力盘点与迁移进度

| 能力 | 原归属 | 当前归属 | 停 WCS 前动作 |
|------|--------|----------|---------------|
| 一键建群 / JS-SDK | WCS 集成 | **DMS** `wecom_client` | ✅ 已完成；去掉 legacy 回退 |
| 绑群台账 | WCS + DMS 双写 | **DMS** `class_workgroups` | 停止同步 WCS 副本 |
| 事件群发（班组/运单/停班） | WCS notify | **DMS** `workgroup_notify` | ✅ 已完成 |
| 智能机器人直推 | WCS aibot | **DMS** `aibot_ws_service` | ✅ 已迁入 |
| 企微 OAuth 绑 userid | WCS 集成 | **DMS** `wecom_client`（经 `wcs_client` 门面） | 门面改名为 `wecom_facade`，删除 WCS 分支 |
| **定时播报**（开课前/每日/结课前） | **WCS** `broadcast_schedule` | **未迁移** | **决策**：迁入 DMS 或放弃（§4.1） |
| FAQ / 知识库 / Coze | **WCS** | **未迁移** | **决策**：放弃或极简化（§4.2） |
| 客户私聊查进度 | **WCS → DMS** `/api/integration/*` | **未替代** | 放弃或 DMS 只读 H5（§4.2） |
| 人工工单 | **WCS** | **未迁移** | 企微群内人工，不入系统 |

代码锚点：

- DMS 门面：`DMS/backend/services/wcs_client.py`（优先本机，WCS 为 legacy）
- DMS 通知：`DMS/backend/services/workgroup_notify.py`
- WCS 定时：`WCS/wcs-gateway/app/services/broadcast_schedule.py`

---

## 3. 分阶段路线图

### Phase 0 · 冻结与口径（立即，1 周）

**目标**：停止新产品叙事上的「三系统并列」，避免继续投入 WCS。

| 动作 | 仓库 | 验收 |
|------|------|------|
| Portal / manual 改为 **TOA + DMS 双系统** 主链；WCS 标「遗留/即将退役」 | `portal/` | 首页流程图去掉 WCS 第三环或改脚注 |
| DMS 登录页去掉「WCS 客服」矩阵入口（或改「已下线」） | `DMS/frontend` | 登录页无 WCS 误导链 |
| 本规划文档入架构索引 | `TOA3/docs/architecture/` | README 已链入 |
| 生产环境：**不再新开 WCS 功能** | 流程 | 发版说明写清 |

**不动**：WCS 进程可继续跑作兜底，直到 Phase 2 完成。

---

### Phase 1 · DMS 企微完全独立（1～2 迭代）

**目标**：DMS 在无 `WCS_BASE_URL` 时全功能可用（建群、绑群、OAuth、事件通知）。

| 动作 | 说明 |
|------|------|
| 生产强制配置 `WECOM_*` + `aibot` 凭证 | `DMS/backend/.env.example` 已有说明 |
| `upsert_binding` 删除「同步 WCS」HTTP 调用 | 消除双写 |
| `wcs_client.notify` 删除 legacy WCS POST | 仅 `workgroup_notify` |
| `auth.py` 企微 OAuth 直调 `wecom_client` | 错误文案改为「未配置企微」 |
| 前端 `wcs_not_configured` / `wcs_configured` 改名 | 如 `wecom_notify_ready` |
| `schemas.py` 注释「真源在 WCS」更正 | 与代码一致 |

**验收**：

-  staging 清空 `WCS_*` 环境变量
- 班级工作台：建群、绑群、班组变更通知均成功
- 登录页企微绑定可用

---

### Phase 2 · 定时播报决策与落地（1 迭代或显式放弃）

**背景**：WCS 独有 **开课前 / 课中每日 / 结课前** 定时群消息；DMS 目前只有 **事件驱动** 通知。

#### 选项 A（推荐，若业务仍要定时提醒）

将 `broadcast_schedule` 逻辑 **迁入 DMS**：

- 新表：`class_broadcast_tasks`（或复用 job_scheduler）
- 调度：`APScheduler` 或 DMS 已有定时任务基础设施
- 发送：复用 `workgroup_notify.notify`
- 上下文：直接读 DMS 班级表，**删除** WCS 调用的 `notify-context` 集成接口依赖

#### 选项 B（简化，若运营接受）

**放弃定时播报**，仅保留事件通知（班组、运单、停班等）+ 运营在群内手工提醒。

| 对比 | A 迁入 DMS | B 放弃 |
|------|------------|--------|
| 客户体验 | 自动提醒仍在 | 依赖运营习惯 |
| 开发量 | 中（移植 scheduler + 管理 UI 可选） | 低 |
| 运维 | 少一套 WCS | 无 |

**主理人须书面择一**；未选前 WCS 仅可为 **定时播报** 保留只读运行。

---

### Phase 3 · 客户侧智能客服下线（2～4 周观察）

**目标**：关闭 WCS 消息回调与知识库，客户不再期待「客服助理自动答」。

| 动作 | 说明 |
|------|------|
| 企微侧：客服应用 / 回调 URL 停用或指向空 | 与企微管理员协调 |
| WCS Gateway 停进程 | `www.yczh.tech` 管理端下线或 410 页 |
| DMS `/api/integration/*`（WCS 只读） | 标记 deprecated；6 个月后删或仅留 health |
| Portal 删除 WCS 产品卡片与手册 §7～§9 | 改为「历史归档」链接 |

**替代方案（§4.2）**：不建 replacement 也可；培训交付以 **客户群 + DMS 推送** 为主路径。

---

### Phase 4 · 仓库与基础设施归档（收尾）

| 动作 | 说明 |
|------|------|
| `WCS/` 仓库打 tag `archive/wcs-final`，只读 | 保留代码备查 |
| nginx：`www.yczh.tech/admin` WCS 路由移除或重定向 Portal | 与 WCS/deploy 文档同步 |
| DMS 删除 `WCS_BASE_URL`、`WCS_INTEGRATION_TOKEN` 及 `wcs_client` legacy 分支 | 可保留模块名 `wecom_facade.py` |
| 监控告警去掉 WCS health | 仅 DMS + 企微 API |

---

## 4. 停 WCS 后的能力取舍（主理人决策点）

### 4.1 定时播报

| 决策 | 后果 |
|------|------|
| **迁入 DMS（Phase 2A）** | 最接近现网体验；开发一次即可永久去掉 WCS |
| **放弃（Phase 2B）** | 最快停 WCS；需在手册写明「重要节点靠 DMS 事件通知 + 运营群公告」 |

### 4.2 客户自助（FAQ / 查进度 / 工单）

| 决策 | 后果 |
|------|------|
| **全部放弃** | 客户群内 @运营；DMS 侧查进度截图/口述。**推荐默认**，符合「弱客服、强交付」 |
| **轻量 H5** | DMS 只读页：输入班级号查摘要（需登录或一次性 token）；无对话 bot |
| **企微原生** | 用企微内置智能助手（不推荐，与历史 WCS 问题同源） |

### 4.3 不建议的方向

- 为「停 WCS」而上 **Portal 统一账号/菜单** — 与已裁定架构冲突  
- 把 TOA 菜单迁到 DMS 远程下发 — 离线桌面弱、发版耦合  
- 用 TOA 替代 DMS 群通知 — 桌面不应成为通知中枢  

---

## 5. 修订后的产品矩阵（对外口径）

### Portal 首页（目标文案）

> **培训交付数字化平台** = **运营宝（TOA）** + **交付材料系统（DMS）**  
> 课前本地效率 · 班级交付与核销 · 企微群触达由 DMS 直连  
> 安装包与手册在本站；业务登录请进 DMS。

### 角色入口

| 角色 | 入口 | 系统 |
|------|------|------|
| 培训运营（课前） | TOA 桌面 | TOA |
| 培训运营（交付） | dms.yczh.tech 管理端 | DMS |
| 助教 | dms.yczh.tech 助教端 | DMS |
| 系统管理员 | DMS 系统设置 + 运营助手授权 | DMS |
| 客户/学员 | 企微客户群（无独立登录） | — |

---

## 6. 风险与回滚

| 风险 | 缓解 |
|------|------|
| 生产未配齐 `WECOM_*` 导致通知全断 | Phase 1 验收必须在无 WCS 环境跑通 |
| 定时播报丢失引发投诉 | Phase 2 主理人明示；或 Phase 2A 完成后再停 WCS |
| 双写绑群不一致 | Phase 1 即停 WCS 同步 |
| 集成 API 被第三方误用 | deprecated 公告 + IP 限制 + 最终下线 |

**回滚**：Phase 3 之前可重新启用 WCS 进程 + 恢复 env；Phase 4 后仅代码归档回滚，需重装 WCS。

---

## 7. 各仓库待办清单（Agent 可接力）

### Portal（`../portal/`）

- [ ] `index.html`：双系统主链；WCS 移入「已退役」或删除
- [ ] `manual.html`：删 WCS 章节或合并为附录；更新 §11 协同为 TOA↔DMS only

### DMS（`../DMS/`）

- [ ] Phase 1：`wcs_client` 去 legacy；绑群停止 sync WCS
- [ ] Phase 1：前端文案 `wcs_*` → `wecom_*`
- [ ] Phase 2A（若选）：迁入 `broadcast_schedule`
- [ ] Phase 3：`/api/integration/*` deprecated 文档

### TOA3（本仓库）

- [ ] `10-必备能力与Portal评估.md`：增「WCS 退役」引用本文
- [ ] `toa3-portal-integration.mdc`：Portal 职责不变；删任何 WCS 并列表述（若有）
- [ ] 检查更新 / About：下载链仍指 Portal，不指 WCS

### WCS（`../WCS/`）

- [ ] Phase 3 后：README 顶置 ARCHIVED
- [ ] 不再接收 feature PR

---

## 8. 时间线建议（可调整）

```text
2026-Q3  Phase 0 口径 + Phase 1 DMS 独立（与 TOA3 体验版发版并行）
2026-Q4  Phase 2 定时播报决策与实现/放弃
2027-Q1  Phase 3  WCS 下线观察
2027-Q2  Phase 4  代码与 nginx 归档
```

---

## 9. 结论

- **停 WCS 与当前代码方向一致**（建群/绑群/事件通知已归 DMS），合理且应推进。  
- **Portal 不必扩大职责**；收敛为入口 + 下载 + 文档即可。  
- **TOA / DMS 账号菜单继续分治**；仅 TOA **授权台账**在 DMS。  
- **唯一硬决策**：定时播报迁 DMS 还是放弃；其余客户自助能力建议放弃以加速退役。

主理人确认 Phase 2（A/B）与 §4.2 后即可排期 Phase 1 开发。
