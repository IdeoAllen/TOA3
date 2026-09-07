# ARCH-04 · TOA 授权与单机/联网模式规划

> **状态**：主理人裁定 · **DMS 与 TOA 为两套独立产品**  
> **版本**：v2 · 2026-08（v1 误将 TOA 商业账本绑在 DMS，已废止）  
> **关联**：`feature_packs.yml` · `license_manager.py` · `access_control.py`

---

## 0. 双产品边界（硬口径）

| | **DMS** | **TOA（运营宝）** |
|---|---|---|
| **产品性质** | 培训 **交付材料采集** Web 系统 | Windows **桌面效率 / 课前工具** |
| **收费** | **免费**（不按模块/SKU 售卖） | **商业产品**（单机免费层 + 联网试用/付费） |
| **账号** | DMS Web 用户 + RBAC | TOA 授权码 / 试用身份 + 本机 `license.json` |
| **菜单** | DMS 角色菜单树 | TOA `app.yml` + `feature_packs` |
| **与对方关系** | **无强绑定** | **无强绑定** |

**禁止再写的口径**：

- ❌ 「TOA 权限以 DMS 为账本」  
- ❌ 「试用/付费走 DMS 运营助手授权」作为 **产品架构**  
- ❌ 未装 DMS / 未登录 DMS 则 TOA 不可用  

**允许的实际协作（弱耦合、可选）**：

- 同一公司内运营人员 **同时** 用 DMS 交付 + TOA 做课前文件（人工上传，无自动同步）  
- Portal 同时提供 DMS 入口链接与 TOA 安装包下载  
- 历史过渡期：DMS 内「运营助手授权」页仅作 **内部发码工具**，不是 TOA 运行时依赖  

---

## 1. TOA 产品目标

| 模式 | 场景 | 网络 | 权限 |
|------|------|------|------|
| **单机模式** | 装完即用、离线 | 不要求 | `local_free` 基础功能 |
| **联网模式** | 完整版、试用、付费、多端 | 连 **TOA 授权服务** | 试用 → 付费 → SKU |

原则：

1. **单机不冒充完整版** — 未激活不得用付费模块。  
2. **联网账本在 TOA 侧** — 独立 **TOA License 服务**（见 §3）；`license.json` 为本地缓存 + 断网宽限。  
3. **菜单在 TOA 本机** — 授权只控制 **能打开哪些 module**（pack / feature）。  
4. **与 DMS 零运行时耦合** — TOA 启动、校验、试用 **不得** 要求 `dms.yczh.tech` 可达。

---

## 2. 四层权限模型（仅 TOA 内部）

```text
L1 运行模式    standalone │ network
L2 entitlement none │ trial │ active │ expired │ revoked
L3 功能范围    local_free │ pack_id… │ all        ← feature_packs.yml
L4 设备策略    不绑机 │ 单绑 │ 多席位（远期）
         ↓
access_control.can_open(module_id)
         ↓
license_manager.has_feature_access(feature_key)
```

### L1 · 运行模式

| 值 | 行为 |
|----|------|
| `standalone` | 仅 `local_free`；**不调用**任何远程授权 API |
| `network` | 调用 **TOA License 服务** activate/check |

启动入口：**单机体验** | **激活 / 开始试用**

### L2 · entitlement（联网，TOA 服务）

| 状态 | 含义 |
|------|------|
| `trial` | 试用中 |
| `active` | 已付费或正式授权 |
| `expired` / `revoked` | 不可用付费模块，回单机层 |

### L3 · SKU（`config/feature_packs.yml` · 现行）

| pack_id | 用途 | sellable |
|---------|------|----------|
| `tiyan` | **全功能方案**（唯一可售；试用与购买均走此 pack；含 `all`） | true |
| `local_free` | 单机免费层（离线基础工具；非售卖入口） | false |
| `extension_studio` | 扩展开发能力（可挂订单 features；常与 harness 一起） | false |

**禁止再写**：`starter` / `professional` / `experience_beta` 作为可售 SKU（已废）。  
用户档位展示文案（基础版/体验版/授权版）见 `services/user_plan_presentation`——**体验版 = 试用档位**，≠ 旧 pack `experience_beta`。

### L4 · 设备

试用/付费默认单绑；企业多席位在 **TOA License 服务** 台账扩展。

---

## 3. TOA 授权服务（独立，非 DMS）

### 3.1 定位

```text
TOA 桌面  ──HTTPS──▶  TOA License API  ◀──  Portal 购买页 / 运营后台
                         │
                    toa_licenses 库（独立库或独立 schema）
```

- **域名**：`https://toa-service.yczh.tech`（`/api/toa-license/*`、`/api/toa/releases/*`、`/admin/`；与 DMS **不同 base URL**）  
- **职责**：发码、试用、升级、check、绑机、吊销  
- **不负责**：DMS 班级、材料、Web 账号  

### 3.2 API（与现 TOA2 协议兼容，从 DMS 迁出）

保留现有终端已实现的语义即可迁移：

| 端点 | 作用 |
|------|------|
| `POST /activate` | 码 + machine_id |
| `POST /check` | 周期校验 |
| `POST /trial-start` | 手机 + machine_id → 试用 |
| `POST /upgrade` | 付费/续费（人工或支付回调） |
| `POST /sync` / `reconcile` | 可选，管理员批量工具 |

配置项从 `license.dms_base_url` **改名为** `license.service_url`（过渡期双读旧键）。

### 3.3 与 DMS「运营助手授权」的关系

| 阶段 | 做法 |
|------|------|
| **现行** | 桌面默认 `license.service_url` → **toa-service**；DMS 发码页仅可选内部工具 |
| **禁止** | 把 DMS 可达当作 TOA 启动前提；新环境勿再配 DMS 为授权账本 |
| **终态** | DMS 删菜单「运营助手授权」或改为 **外链** 到 TOA 运营台；DMS 库无 `toa_licenses` |

TOA **必须** 在无 DMS 部署的机器上完整可用（单机层 + 联网连 License 服务）。

---

## 4. 推广闭环（TOA 商业，与 DMS 无关）

```text
安装 TOA → 单机 local_free
         → 联网 trial-start（TOA License API）
         → 到期 → Portal 购买说明 / 支付回调 → upgrade
         → check 刷新 features
```

| 阶段 | 入口 |
|------|------|
| 试用 | TOA 内「开始试用」→ License API |
| 付费 v1 | Portal 页 + 人工开单 → 运营台写台账 |
| 付费 v2 | 支付回调 → License API `upgrade` |

**DMS 不参与收费、不提供 TOA SKU。**

---

## 5. DMS 侧（免费产品，保持简单）

- Web 账号 + RBAC：**仅 DMS 功能**，与 TOA features 无关  
- **无** TOA 模块门禁、**无** 按模块售卖  
- 与 TOA 协作：业务上「TOA 生成 → 人工上传 DMS」，技术上 **无 API 硬依赖**  

WCS 退役后，DMS 仍 = 交付 + 企微触达（归档说明见 `docs/_archive/architecture/`，不作现行门禁）。

### 代码入口（现行）

| 职责 | 路径 |
|------|------|
| 对外推荐入口 | `services/license_client.py` |
| 本机态 / 激活 | `services/license_manager.py` · `services/auth_service.py` |
| 功能门禁 | `services/access_control.py` + `feature_packs.yml` |
| 本机缓存 | `config/license.json`（**禁止提交 git / 禁止打进安装包**） |

---

## 6. Portal 角色（修订）

| 职责 | 说明 |
|------|------|
| TOA 安装包下载 | 是 |
| DMS / TOA 产品说明与链接 | 是 |
| TOA 购买 / 试用说明 | 是（算 TOA 商业入口） |
| TOA / DMS 统一账号 | **否** |
| TOA / DMS 统一菜单 | **否** |
| DMS 业务 API | **否** |

---

## 7. 代码现状 vs 目标（迁移清单）

### 7.1 现状（过渡，易误解为强绑定）

- `license.dms_base_url` → 指向 DMS  
- `dms_license_client.py` / DMS `toa_licenses` / `AdminToaLicense.vue`  
- 激活失败提示「连 DMS」  

### 7.2 目标

| 项 | 动作 |
|----|------|
| 配置 | `license.service_url` 默认 **`https://toa-service.yczh.tech/api/toa-license`**（与 `config/app.yml` 一致；**禁止**再写 `license.yczh.tech`） |
| 客户端 | 入口 `services/license_client.py`（包装历史实现） |
| 服务 | License API 已挂 toa-service；DMS 内 toa_license **deprecated** |
| 门禁 | `access_control` + `feature_packs`（`tiyan` / `local_free`） |
| 登录窗 | 单机 / 激活 / 试用；文案不出现「DMS 账本」 |
| 离线 | 仅依赖 License 服务宽限，与 DMS 无关 |

### 7.3 实施顺序

```text
1. 文档与配置口径（本文 + 规则）— 已完成 v2
2. TOA：local_free + access_control + 登录窗单机入口
3. 部署 TOA License 服务（迁表 + API）
4. TOA 客户端改 service_url；DMS 发码页改外链或只读
5. 移除 DMS 对 toa_licenses 的运行时依赖
```

---

## 8. license.json（TOA 本地，不变）

```json
{
  "runtime_mode": "standalone | network",
  "entitlement": "none | trial | active | expired | revoked",
  "plan_id": "local_free | tiyan",
  "features": ["all"],
  "license_service_url": "https://toa-service.yczh.tech"
}
```

---

## 9. 主理人待确认（TOA 专属）

1. `local_free` 模块清单  
2. 试用天数 / 次数  
3. License 服务挂 **独立子域** 还是 **Portal 后端**  
4. 过渡期内是否保留 DMS 发码页给内部用  

DMS / Portal / WCS 边界问题 **不在本文收费模型内**——DMS 始终免费。
