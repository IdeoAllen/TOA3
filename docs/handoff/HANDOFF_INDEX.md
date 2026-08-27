# TOA3 · Agent 交接总册（规范 / 规则 / Skill / 愿景 / 要求）

> **新 Agent / 新会话：先读本文件，再读任务进度。**  
> 仓库根：`C:\Users\43594\Desktop\YCZH-TDP\TOA3`  
> 更新：2026-08-25  
> 配套进度文件：[`AGENT_RELAY.md`](./AGENT_RELAY.md)（当前做到哪、下一步做什么）

---

## 0. 开场 30 秒

| 问 | 答 |
|----|----|
| 产品是什么 | 办公极简伴侣（TOA3 / 运营宝），PySide6 桌面端 |
| 要成为谁 | 办公室人员安装即集成剪贴板/截图/目录/文件/桌面/业务等效率工具；最爱、最方便的桌面办公伴侣 |
| 口号 | **办公极简伴侣 · 少点一下，多干一件事** |
| 只改哪里 | **只改 TOA3**；`../TOA`（TOA2）封板只读逻辑，禁止扩功能 / 禁止重写 tk UI |
| 当前主线 | Wave★ 个人八件套，现卡在 **screenshot_tool** 做强验收 |
| 写码前门禁 | Top3 对标 + **恰好 3 条独到处经主理人确认** → 才实现 |
| 完成标准 | `gaps` 空 **且** 主理人认可「每天愿意用」才标 `done` |

---

## 1. 愿景与产品要求（必须对齐）

### 1.1 真相源

| 层级 | 路径 | 说明 |
|------|------|------|
| 运行时文案 | `config/product.yml` → `vision:` | 首页 / 关于弹窗同源 |
| 加载 | `services/product_vision.py` | |
| 文档公示 | `docs/产品愿景.md` | 给人看的副本；改文案只改 yml |

### 1.2 愿景摘要（勿擅自改写对外口径）

- **愿景**：让办公人员感到极致简便——打开就能用，用完不想换别的软件。  
- **目标**：成为办公室工作人员最爱、最方便、最离不开的桌面办公软件。  
- **受众**：培训运营、教务、行政与通用白领。  
- **承诺**：高频刚需做强；键位跟手、步骤少；本地优先可离线；截图/记事/剪贴板一站直达。  
- **命名**：正式俏皮名待共创；现阶段「运营宝 / TOA」。

### 1.3 产品六项核心（开发总纲）

出处：`.cursor/rules/toa3-product-core.mdc` · `docs/architecture/11-产品核心规范.md`

1. 风格统一、专业（全局 QSS + widgets；禁硬编码色 / 散落 setStyleSheet）  
2. 简捷实用（单模块单主任务）  
3. 架构清晰、可扩展（分层 + BasePage 登记）  
4. 安全可靠（license/DMS；路径走 storage_paths）  
5. 三方统一（仅 `services/integrations`）  
6. 异常与窗口统一（error_handler + ui_spec + 主题弹窗）  
7. **Top3 + 三独到处**（开工前共创确认）  
8. **验收不回退**（gaps / 状态灯 / skill）

### 1.4 推进优先级要求

出处：`.cursor/rules/toa3-personal-priority.mdc` · `docs/功能清单与优先级.md` §0.5

**Wave★ 顺序（未达标前不扩培训主链）：**

1. `screenshot_tool` → 2. `clipboard_history` → 3. `quick_notepad`  
4. `quadrant_tasks`（missing） → 5. `watermark_remover` → 6. `image_watermark`  
7. `directory_generator` → 8. `screenshot_translate`（挂截图，勿空菜单）

降级：`pomodoro` / `image_creator` 等非八件套 → P2/Hold。

---

## 2. Cursor Rules（全部须遵守；按场景加载）

目录：`.cursor/rules/toa3-*.mdc`（共 17 条）

### 2.1 alwaysApply（任何任务默认生效）

| 规则文件 | 一句话 |
|----------|--------|
| `toa3-boundary.mdc` | 主开发线在 TOA3；TOA2 封板不扩功能 |
| `toa3-product-core.mdc` | 产品六项核心 + Top3/验收总纲 |
| `toa3-architecture-layers.mdc` | 分层单向依赖：modules → widgets → core/app → services → config |
| `toa3-personal-priority.mdc` | Wave★ 八件套优先顺序 |
| `toa3-feature-top3-research.mdc` | **未论证三独到处不得写码** |
| `toa3-feature-acceptance.mdc` | HiDPI / 性能 / 状态灯 / 联调闭环 |
| `toa3-portal-integration.mdc` | license 走 DMS；菜单本地 yaml |
| `toa3-office-suite-shell.mdc` | **安装=办公套件集成**；一级顶栏子模块（子系统）/二级功能模块/系统介入 |

### 2.2 按文件匹配（改对应路径时必读）

| 规则文件 | 何时 |
|----------|------|
| `toa3-control-library.mdc` | 改 `modules/**` / `widgets/**` / UI |
| `toa3-errors-and-windows.mdc` | 弹窗、异常、`ui_spec` |
| `toa3-storage-layout.mdc` | 读写文件、模板、`storage.yml` |
| `toa3-config-paths.mdc` | 配置、`TOA_ENV`、路径解析 |
| `toa3-desktop-services.mdc` | 托盘、热键、截图、单实例 |
| `toa3-integrations.mdc` | 三方 API |
| `toa3-license-dms.mdc` | 登录、授权账本 |
| `toa3-module-migration.mdc` | 新模块 / stub→实装 / `MIGRATED_MODULES` |
| `toa3-testing.mdc` | 测试脚本、发版前门禁 |
| `toa3-packaging-release.mdc` | PyInstaller / Inno / 版本 |

### 2.3 铁律摘录（高频踩坑）

- 业务页 **只用 `widgets/`**；主题预览页 = 控件库验收面  
- 禁止裸 `QMessageBox`；用 `core.user_messages` / `BaseDialog`  
- 禁止进页同步联网探测；热键路径不阻塞  
- 截图/自绘：逻辑像素 + DPR；工具栏防全局 QSS 撑高  
- 弹窗默认屏幕居中（`center_on_screen`）  
- 改主题 token → `python scripts/gen_qss_from_theme.py`  
- 菜单入口只来自 `config/app.yml` / `data/user/menu.yml`，禁止壳内写死列表  

---

## 3. Skill（强制流程）

| Skill | 路径 | 何时使用 |
|-------|------|----------|
| **toa3-add-feature** | `.cursor/skills/toa3-add-feature/SKILL.md` | 新功能 / 做强 / 迁移模块 / 用户说「开工」 |

**强制顺序（不可跳）：**

0. 读 Top3 / 验收 / 控件库 / 分层规则  
1. 定场景（谁/何时/输入/输出）  
2. 写 `docs/research/<module_id>-top3.md` → 主理人确认 3 条独到处 → `approved`  
3. 技术方案一页纸  
4. 实现（BasePage、菜单、storage、manifest）  
5. `verify_all` + `audit_migration` + 人工点验  
6. gaps 清空且主理人认可才 `done`

模板：`docs/research/_TEMPLATE-top3.md`  
已批准范例：`docs/research/screenshot_tool-top3.md`（`approved`）

---

## 4. 开发规范文档（standards + architecture）

### 4.1 起手与标准

| 文档 | 用途 |
|------|------|
| `docs/standards/Agent起手式.md` | 新会话起手、仓库命令、批次编排 |
| `docs/standards/UI架构.md` | UI 铁律摘要 |
| `docs/standards/控件库规范.md` | 控件选用清单 |
| `docs/standards/快捷键规范.md` | G/A/P 分层热键 |

### 4.2 架构（`docs/architecture/`）

| 文档 | 用途 |
|------|------|
| `README.md` | 索引 |
| `01`–`03` | 总览、分层、壳与导航 |
| `04`–`05` | 主题 QSS、控件库 |
| `06`–`07` | 业务模块、配置与数据 |
| `08`–`09` | 测试验收、打包发布 |
| `10` | 必备能力 / Portal / P0 |
| `11` | 产品核心规范（详） |
| `12` | 平台层开发计划 |
| `13` | 白领增效与能力扩展 |

### 4.3 清单与进度

| 文档 | 用途 |
|------|------|
| `docs/功能清单与优先级.md` | Wave★ / P0–P2 真相源 |
| `docs/已实现功能确认清单.md` | 灯色与缺口 |
| `docs/迁移进度.md` | 迁移摘要 |
| `config/migration_manifest.yml` | 模块 stub/mvp/done + gaps |
| `docs/handoff/AGENT_RELAY.md` | **当前迭代进度与待办** |

---

## 5. 验收与质量要求

出处：`toa3-feature-acceptance.mdc` · `docs/architecture/08-测试与验收.md`

| 要求 | 标准 |
|------|------|
| 状态灯 | `done` ⇔ 核心可用且 gaps 空；有缺口 = `mvp` |
| 性能 | 进页/热键禁同步联网；重页懒加载 |
| HiDPI | 截图/自绘 1:1，工具栏不撑高 |
| UI | `page_content_margins`；弹窗 `BaseDialog`；跟主题 |
| 联调 | 改完重启 → 主理人点验 → 回写 gaps |
| 脚本 | `python scripts/verify_all.py` · `audit_migration` · `audit_architecture` |

**主观门槛**：主理人愿意「每天用」才算 Wave★ 项完成。

**超边门禁（架构先行）**：详见 [`docs/architecture/14-超边门禁与目标锁定.md`](../architecture/14-超边门禁与目标锁定.md)。增强功能 = Top3 独到处 **且** 超边自检通过。

---

## 6. 工程约定速查

```
分层：modules → widgets/ui → core/app → services → config
页面：core.base_page.BasePage
弹窗：core.base_dialog.BaseDialog（showEvent 居中）
提示：core.user_messages
路径：services.storage_paths + config/storage.yml
主题：config/themes/*.json → scripts/gen_qss_from_theme.py → resources/qss/
启动：scripts/start_toa3.ps1  或  python -m app.main（须含 PySide6）
日志：common/logs/toa3.log
超边审计：scripts/audit_architecture.py
```

工作区外相关（只读 / 另仓规则）：

- TOA2 封板：`../TOA`  
- DMS 发布门禁：工作区上级 `.cursor/rules/dms-release-deploy.mdc`（**与 TOA3 功能开发无关时勿动**）

---

## 7. 新 Agent 开场检查单

复制到会话开头自检：

- [ ] 已读本总册 §0–§3（愿景 / 规则 / skill）  
- [ ] 已读 [`AGENT_RELAY.md`](./AGENT_RELAY.md) 知当前任务  
- [ ] 已扫 [`14-超边门禁与目标锁定.md`](../architecture/14-超边门禁与目标锁定.md) 判定表  
- [ ] 确认只改 `TOA3`  
- [ ] 若增强功能：已打开 `toa3-add-feature` skill；Top3 未 `approved` 不写业务码  
- [ ] 控件只用 widgets；弹窗走 BaseDialog；路径走 storage_paths  
- [ ] 不擅自把模块标 `done`  
- [ ] 不跳过 Wave★ 顺序（除非主理人当次明确改口）  
- [ ] Wave B / 发版工程不插队八件套  

---

## 8. 修订记录

| 日期 | 摘要 |
|------|------|
| 2026-08-25 | 初版：愿景、17 条 rules、skill、standards/architecture、验收要求一册交接 |
| 2026-08-25 | 架构先行：链到 14-超边门禁；开场检查单补超边/WaveB 门禁 |
