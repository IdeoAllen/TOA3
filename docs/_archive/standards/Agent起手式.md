# TOA3 新 Agent 开发起手式

> **用途**：新会话 / 新 Agent 开发前 **先读本文**，再读规则。  
> **交接入口（必读）：**  
> 0. [`docs/README.md`](../README.md) — **文档宪法（现行官方唯一表）**  
> 1. [`docs/handoff/HANDOFF_INDEX.md`](../handoff/HANDOFF_INDEX.md) — 愿景 / 规则 / Skill / 规范  
> 2. [`docs/handoff/AGENT_RELAY.md`](../handoff/AGENT_RELAY.md) — **唯一进度文件**  
> **禁止**另建规划 / 总览 / 方案副本。

---

## 1. 当前上下文评估（2026-08-25）

### 已完成（可视为「壳 MVP 封板」）

| 领域 | 状态 |
|------|------|
| 主壳 | 菜单/工具栏/侧栏/状态栏/模块切换 |
| 主题 | 11 官方 JSON→QSS，设置页即时换肤 |
| 控件库 | gallery 验收面 |
| 配置/路径 | `resolve_path`、`storage_paths`、`assets/` 分层 |
| 异常/窗口 | `error_handler`、`ui_spec.yml`、`BasePage`/`BaseDialog` |
| 三方骨架 | `integrations.yml` + DMS 客户端占位 |
| 验收 | `scripts/verify_all.py` |
| Agent 规则 | 14 条 `.cursor/rules/toa3-*.mdc` |
| 架构文档 | `docs/architecture/01–11` |

### 未完成（完整迁移 / 生产前 P0）

| 领域 | 说明 | 参考 TOA2 |
|------|------|-----------|
| DMS 授权实装 | `auth_service` 仍为 stub | `common/license_manager.py`, `dms_license_client.py` |
| 导航门禁 | `requires_license` / features | `common/access_control.py` |
| 运行时路径 | `%LOCALAPPDATA%` 冻结包 | `common/runtime_paths.py` |
| 托盘/全局热键/截图 | 壳内快捷键 only | `tray_icon`, `hotkey_manager`, `wechat_screenshot` |
| 打包 | 无 spec/ISS | `packaging-app/` |
| 业务模块 | **3/16+ 可见菜单** 实装，其余 Stub | `modules/*` |
| 列表/编辑弹窗 | 未建 widgets | `ui_list_edit`, `BaseEditDialog` |
| integrations 实装 | DMS activate/check 抛「待移植」 | — |

### 工作量粗估

- **P0 基础设施**：约 1–2 个专职 Agent 会话（授权+路径+托盘热键+打包骨架）
- **单业务模块迁移**：0.5–2 会话/模块（视 TOA2 UI 复杂度）
- **16 可见菜单全迁**：**多个 Agent 会话**，不宜在当前超长上下文续写

**裁定**：**规成标准文档 → 新 Agent 按批次开发**（本文 + 架构 10/11 + rules）。

---

## 2. 仓库与命令

```text
主开发：C:\Users\43594\Desktop\YCZH-TDP\TOA3
封板参考：C:\Users\43594\Desktop\YCZH-TDP\TOA（只读逻辑，UI 不重写 tk）
DMS：C:\Users\43594\Desktop\YCZH-TDP\DMS（授权 API、发版）
```

```powershell
cd C:\Users\43594\Desktop\YCZH-TDP\TOA3
pip install -r requirements.txt
python scripts/verify_all.py          # 改动后必跑
python scripts/sync_assets_from_toa2.py  # 缺模板时
python -m app.main                    # 人工验收
```

---

## 3. 开发铁律（摘要）

1. **只改 TOA3**；TOA2 封板不扩功能  
2. **分层**：`modules → widgets/ui → core/app → services → config`  
3. **无硬编码色**；无页面 `setStyleSheet`  
4. **路径**：`services.storage_paths`；**异常**：`core.error_handler`  
5. **窗口**：`config/ui_spec.yml`；**三方**：`services.integrations`  
6. **新模块**：`BasePage` + `storage.yml` 登记 + `MIGRATED_MODULES`  

完整条文：`.cursor/rules/toa3-product-core.mdc`（alwaysApply）

---

## 4. 推荐任务编排（新 Agent 按序执行）

### 阶段 A — 生产门禁（优先于大批量迁模块）

1. 移植 `license_manager` + `dms_license_client` → `services/license/`  
2. 登录窗接真实授权；`access_control` 过滤侧栏/菜单  
3. 移植 `runtime_paths` + 单实例  
4. 托盘 + 全局热键 + 截图（可拆 3 个小任务）  
5. `packaging/` PyInstaller + Inno，`APP_VERSION` 对齐  

每步结束：`verify_all` + 更新 `10-必备能力与Portal评估.md` 矩阵状态。

### 阶段 B — 公共 widgets（迁模块前建议）

- `widgets/dialogs.py`（`EditDialog`、`confirm`）  
- `widgets/list_panel.py`（对标 `BaseListPanel`）  
- `widgets/path_row.py`（路径行 + 浏览）  
- gallery 各补一节  

### 阶段 C — 业务模块（按价值排序）

| 优先级 | module_id | TOA2 入口 |
|--------|-----------|-----------|
| C1 | `deduction_note_formatter` | `modules/deduction_note_formatter/`（热键唤起） |
| C2 | `table_card_generator` | `modules/table_card_generator/` |
| C3 | `directory_generator` | `modules/directory_generator/` |
| C4 | `directory_inspector` | `modules/directory_inspector/` |
| C5 | `image_to_scan` | `modules/image_to_scan/` |
| … | 其余可见菜单 | `config/app.yml` menu_items |

**单模块 checklist**（每模块开 Agent 时复制）：

```markdown
- [ ] 读 TOA2 模块 page + 逻辑文件，拆 service
- [ ] `ui/modules/<id>/page.ui` + `modules/<id>/page.py` extends BasePage
- [ ] `config/storage.yml` 登记 templates/samples
- [ ] `MIGRATED_MODULES` 登记
- [ ] 仅用 widgets + gallery 控件
- [ ] 导出走 `module_output_dir(id)`
- [ ] `verify_all` 通过
- [ ] 人工点验 3 条主路径
```

---

## 5. 新 Agent 首条 Prompt 模板（复制即用）

```text
在 TOA3（C:\Users\43594\Desktop\YCZH-TDP\TOA3）开发。

先读：
- docs/standards/Agent起手式.md
- docs/architecture/11-产品核心规范.md
- .cursor/rules/toa3-product-core.mdc

任务：[填写：如「阶段 A-1 移植 DMS license」或「阶段 C1 迁移 deduction_note_formatter」]

约束：
- 遵守全部 toa3-*.mdc 规则
- 结束跑 python scripts/verify_all.py
- TOA2 只迁逻辑，UI 用 PySide6 + widgets
- 不要改 TOA2 封板仓库
```

---

## 6. 文档索引

| 文档 | 何时读 |
|------|--------|
| [Agent起手式.md](Agent起手式.md) | **每个新 Agent 第一条** |
| [architecture/README.md](../architecture/README.md) | 架构总览 |
| [10-必备能力与Portal评估](../architecture/10-必备能力与Portal评估.md) | P0 缺口 |
| [11-产品核心规范](../architecture/11-产品核心规范.md) | 六项核心 |
| [06-业务模块规范](../architecture/06-业务模块规范.md) | 迁模块结构 |
| [控件库规范.md](控件库规范.md) | 控件选用 |

---

## 7. 人工验收最小集（壳 MVP 已验收后可进入迁移）

- [ ] `verify_all` 绿  
- [ ] 首页 / 控件库 / 系统设置换肤  
- [ ] 侧栏 16 项可进（stub 不崩）  
- [ ] 状态栏版本 `3.0.0-MVP`  

通过后：**不要在本会话硬迁全部模块** → 用 §5 Prompt 开新 Agent。
