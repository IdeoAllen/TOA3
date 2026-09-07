# STD-01 · TOA3 工程标准与流程

> **文档编号**：STD-01  
> **体系**：TOA3 桌面端程序开发规范（PySide6/Qt；对标传统 WinForm 桌面规范结构）  
> **效力**：自 **2026-09-07** 起为工程侧 **唯一**标准+流程正文；旧分册/旧标准已归档下线（`docs/_archive/OFFLINE.md`）。  
> **冲突裁决**：代码实现 > 本文 > `.cursor/rules/toa3-*.mdc`（规则仅为短强制提醒）。  
> **不作门禁**：`docs/_archive/`、会话纪要、Cursor plan、任何未编号旧文件名。  
> **意见回写**：主理人反馈 → 改本文 A/B 或对应 SOP（SOP-07）；禁止只改聊天记录。  
> **配套**：`docs/规范/00-规范清单.md` · SOP · Skill `toa3-sop-*` / `toa3-dev-suite`  
> **架构专题**：`docs/architecture/ARCH-*.md` — 产品/授权裁定以 ARCH 为准；工程门禁以本文为准。  
> 更新：2026-09-07

```powershell
cd C:\Users\43594\Desktop\YCZH-TDP\TOA3
python scripts/verify_all.py
python -m app.main
```

---

# A. 标准（必须成立的事实）

## A0. 总则

| ID | 标准 |
|----|------|
| A0.1 | 只改本仓库 TOA3；TOA2（`../TOA`）封板，可只读移植逻辑，禁止重写 tk UI。 |
| A0.2 | 版本号唯一真相：`app/version.py` → `APP_VERSION`。 |
| A0.3 | 排期只改 `docs/PROD-01-功能清单与优先级.md`；进度只改 `docs/handoff/OPS-01-交接与进度.md`；产品叙事只改 `docs/PROD-02-商务产品手册.md`；运行时愿景文案只改 `config/product.yml`。 |
| A0.4 | 禁止新建「总览/规划2/指针页」；禁止往 `docs/` 写 Excel/Figma brief（导出仅 `output/`）。 |
| A0.5 | 产品定位：安装 TOA3 = 集成常用办公效率工具；菜单可发现 + 系统可唤起（热键/托盘/覆盖层至少一种，Wave★ 必选）。 |
| A0.6 | **只认新规范**：开发/验收/Agent 作业只依据 `docs/规范/` + `ARCH/PROD/OPS`；禁止引用 `_archive/` 或已下线文件名当依据。 |
| A0.7 | **意见入库**：主理人对规范/流程的反馈，必须在当次或紧随会话写入 STD/SOP/ARCH/PROD 对应文件并更新 OPS-01 一句；禁止「知道了」却不改规范。 |

## A1. 分层与依赖

```
modules/*  →  widgets/* + ui/*.ui  →  app/shell · theme_loader · core/* · module_loader
           →  services/*  →  config/* · resources/qss
```

| ID | 标准 |
|----|------|
| A1.1 | 依赖只允许向下；`services/` 不得依赖 `modules/` 或 `widgets/`。 |
| A1.2 | 禁止业务页 `setStyleSheet`、硬编码色值、裸 `QPushButton` 作主按钮。 |
| A1.3 | 禁止在 `modules/` 另建控件库；禁止用 `QTabWidget` 作模块外壳。 |
| A1.4 | 禁止手改 `resources/qss/*.qss`；须改主题 JSON 后生成。 |

## A2. 壳、导航、介入

| ID | 标准 |
|----|------|
| A2.1 | 一级子模块 = 顶栏 Tab（`group_id` / `select_domain`）；二级功能模块 = 侧栏；三级任务页 = `BasePage`。 |
| A2.2 | 菜单条目只来自 `config/app.yml` 或 `data/user/menu.yml` + `menu_registry`；禁止业务页/`home_page` 写死工具列表。 |
| A2.3 | 模块切换仅 `app/shell.py`：`MainShell` + `QStackedWidget` 懒加载。 |
| A2.4 | Overlay 必须 Esc/完成可退；热键/进页路径禁止同步长联网；不造第二菜单。 |
| A2.5 | 「账号」「关于」为顶栏弹窗，不进侧栏堆栈。 |

详表与现状：`docs/architecture/ARCH-02-办公套件壳层.md`。

## A3. 页面、控件、颜色、密度、图标、热键

### A3.1 页面与提示

| ID | 标准 |
|----|------|
| A3.1.1 | 业务页继承 `core.base_page.BasePage`；边距用 `page_content_margins()` / `apply_standard_page_layout()`，禁止贴边 `margins(0)`。 |
| A3.1.2 | 弹窗：`BaseDialog` / `FormEditDialog`；禁止业务页散落 `QMessageBox`。 |
| A3.1.3 | 用户提示：`core.user_messages`（`show_info` / `show_error` / `show_warning` / `ask_confirm`）。 |
| A3.1.4 | **生成完成**必须 `show_saved(parent, text, path)`；禁止用蓝色 `show_info` 冒充。 |
| A3.1.5 | 状态：`BasePage.report_status`；焦点：覆写 `primary_focus_widget`，`__init__` 末 `apply_page_focus_policy()`。 |
| A3.1.6 | 控件高度跟 `widgets/metrics.py`；弹窗尺寸 `apply_dialog_spec`。 |

### A3.2 控件库

| ID | 标准 |
|----|------|
| A3.2.1 | 业务页只用 `widgets` 导出控件；登记真相源：`widgets/__init__.py` → `CONTROL_CLASSES`。 |
| A3.2.2 | 未入 `CONTROL_CLASSES` 且未在 gallery 展示的控件，禁止业务引用（例外须注释 `# 控件库例外：…`）。 |
| A3.2.3 | `ComboBox` 默认 `minWidth≥180`、`minimumContentsLength≥14`；`MenuButton` 须 `hasMenu` + QSS `::menu-indicator`。 |

### A3.3 颜色与主题

| ID | 标准 |
|----|------|
| A3.3.1 | 颜色/字号只来自 `config/themes/<id>.json` 的 `palette`（及主题内 typography）；业务不读 hex。 |
| A3.3.2 | 换肤管线：改 JSON → `python scripts/gen_qss_from_theme.py` → `resources/qss/` → `theme_loader.apply_theme`。 |
| A3.3.3 | 表格选中必须用 `row_selected`，禁止系统亮蓝。 |
| A3.3.4 | 参考全键：`config/themes/toa_complete.json`。 |

**语义色键（只认键名）**

| 语义 | 键 | 用途 |
|------|-----|------|
| 主色 | `primary` / `_hover` / `_pressed` | 主按钮、强调、进度 |
| 表面 | `background` / `surface` / `surface_*` | 底与面板 |
| 文字 | `text_primary` / `text_secondary` / `text_disabled` / `text_on_primary` | 层级 |
| 边框 | `border_default` / `border_strong` / `border_focus` / `border_input` | 线与焦点 |
| 表格 | `row_*` / `row_selected` | 列表 |
| 壳 | `header_*` / `nav_*` | 顶栏侧栏；业务勿自造第二套 |
| 语义 | `success*` / `warning*` / `danger*` / `info*` | 完成/警告/危险/信息 |

### A3.4 工作区密度

| ID | 标准 |
|----|------|
| A3.4.1 | 正文是主角；侧栏已有模块名则默认不设长 `PageHeader` hint。 |
| A3.4.2 | 主工具条最多 1 行；首屏非正文行目标 ≤3。 |
| A3.4.3 | `FormSection` 标题与区内 Hint 不得同义重复；非常用进「更多」。 |

### A3.5 图标

| ID | 标准 |
|----|------|
| A3.5.1 | 统一 `services/icon_registry`（`get_icon` / `icon_pixmap`）；侧栏/顶栏/卡片用 SVG。 |
| A3.5.2 | 按物理像素光栅化并设 DPR；禁止对逻辑尺寸 pixmap 再放大导致发虚。 |
| A3.5.3 | 125%/150%/200% 缩放下目测锐利。 |

### A3.6 快捷键

| ID | 标准 |
|----|------|
| A3.6.1 | 配置真相源：`config/app.yml` → `hotkeys`（开发可用 `app.dev.yml` 覆盖）。 |
| A3.6.2 | 优先级：页内 > 应用 > 全局；输入框内字母键让给打字。 |
| A3.6.3 | 全局键须带 Alt/Ctrl；禁止裸字母全局墙；不占用 `Ctrl+C/V/X/Z/A`、`Alt+F4`、`Win+…`。 |
| A3.6.4 | `Alt+A` = 立刻区域截图（禁止只打开模块页）；`Ctrl+H` 仅应用内，禁止 RegisterHotKey。 |

## A4. 生命周期与性能

| ID | 标准 |
|----|------|
| A4.1 | `__init__` 只建 UI；禁止同步联网、读大文件、起重进程。 |
| A4.2 | `on_enter` 刷新/探活必须异步；`on_leave` 停表/取消/释放，异常不得拖垮壳。 |
| A4.3 | 耗时 IO/推理：`QThread`（或等价）+ `Signal` 回 UI；worker 禁止直接改控件。 |
| A4.4 | 主路径低配可用；GPU/大模型仅为可选增强，失败安静回退。 |
| A4.5 | 探索路径：一件安装 + 配置 ≤2 步；主路径不因未探索而不可用。 |
| A4.6 | 截图/自绘：逻辑像素几何 + 正确 `devicePixelRatio`；工具栏按钮 `padding:0` + 固定高宽。 |

## A5. 数据落盘（本机数据设计）

本产品**不设**客户端 RDBMS/ER 规范。持久化为 JSON/YAML，路径经 `services/storage_paths`。

| ID | 标准 |
|----|------|
| A5.1 | 运行数据：`module_data_dir(id)`；生成物：`module_output_dir(id)`；目录登记：`config/storage.yml`。 |
| A5.2 | 禁止业务手写绝对路径、往安装目录或仓库根乱写用户数据。 |
| A5.3 | 开发版仓库 `data/` 与正式版用户目录（如 `%LOCALAPPDATA%\YCZH-TOA3`）**不共用**。 |
| A5.4 | 用户偏好只写 `writable_config_path()` / `data/user/*.yml`；禁止整文件覆盖带注释的仓库 `config/app.yml`。 |
| A5.5 | `TOA_ENV=release` 不加载 `app.dev.yml`。 |
| A5.6 | 大文件有上限；密钥不得写入业务 JSON（见 A6）。 |

## A6. 接口与密钥

| ID | 标准 |
|----|------|
| A6.1 | 出站 HTTP 只经 `services.integrations.get_client`；声明在 `config/integrations.yml`（无密钥）。 |
| A6.2 | LLM 等密钥：`data/user/integrations_secrets.json`；Harness 凭证走 DSH credentials 桶；两桶不得混写。 |
| A6.3 | 禁止把 Key 写入 `config/*.yml`、源码、日志、安装包。 |
| A6.4 | TOA License / 发版基址：`https://toa-service.yczh.tech`（`license.service_url` 指向 `/api/toa-license`）；禁止把 DMS 当 TOA 账本。 |
| A6.5 | 用户扩展桥：扩展内 `HOST_API.md` + `toa_bridge.js`（见 architecture/28）。 |
| A6.6 | Harness 默认 `surface_mode: browser`（见 `config/harness.yml`）；`engine_host_hub` 为 Hold。 |

## A7. 日志、异常、审计

| ID | 标准 |
|----|------|
| A7.1 | 初始化：`app.logging_setup.setup_logging` → `common/logs/toa3.log`（轮转）。 |
| A7.2 | 业务用 `logging.getLogger`；禁止 `print` 当诊断。 |
| A7.3 | 用户操作审计：`core.audit_log.audit` → `TOA3.audit`。 |
| A7.4 | 异常经 `core.error_handler`；用户只看友好句，detail 进日志；禁止日志打完整 Key。 |

## A8. 版本与打包

| ID | 标准 |
|----|------|
| A8.1 | 打包入口：`packaging/build_windows.py` + Inno；发版配置用 `packaging/shipped_config/*`。 |
| A8.2 | 禁止打进包：`data/user`、`license.json`、`app.dev.yml`、secrets、本机日志。 |
| A8.3 | 生产包禁止 `auth.skip_login`。 |
| A8.4 | 发版护栏：`packaging/release_config_guard.py`；版本对齐：`scripts/sync_release_version.py`。 |

## A9. 授权与菜单可见性

| ID | 标准 |
|----|------|
| A9.1 | SKU：`config/feature_packs.yml` — 可售 `tiyan`；单机层 `local_free`；禁止再引入 `starter`/`experience_beta` 可售包。 |
| A9.2 | 门禁：`access_control` + license；入口推荐 `services/license_client.py`。 |
| A9.3 | 侧栏仅显示 `show: true` 且 manifest/license 允许的模块；未验收不得盲目 `show: true`。 |

## A10. 完成灯与 Git

| ID | 标准 |
|----|------|
| A10.1 | `migration_manifest`：`done` = 核心可用 **且** `gaps` 为空且主理人认可；有缺口一律 `mvp`。 |
| A10.2 | 禁止「有页面就标 done」；未过 Top3+三独到处不得把 Wave★ 标 `done`。 |
| A10.3 | 禁止提交：`config/license.json*`、`integrations_secrets*`、`.env*`、`data/module/**` 运行时、`common/logs/**`、`output/**`（除 README）。 |

---

# B. 流程（如何做）

## B1. 新功能 / 做强（强制顺序，不可跳）

**适用**：新模块、大增强、TOA2 迁移业务。Skill：`toa3-sop-new-feature`。

| 步 | 动作 | 完成判据 |
|----|------|----------|
| 1 | 定场景：谁 / 何时 / 输入 / 输出 / 失败提示 | 与主理人一句话对齐 |
| 2 | Top3 对标 + 草案恰好 3 条独到处 | 写入 `docs/research/<id>-top3.md` |
| 3 | 与主理人逐条论证独到处 | 文档勾选确认；状态 → `approved` |
| 4 | 技术方案（同 research 文档）：栈 / 否决 / 落点 / 性能 / 验收步骤 | 可测、可交付 |
| 5 | 实现：兑现 3 条独到处；遵守 **A** 全部适用条款 | 代码可运行 |
| 6 | 登记：菜单 + `MIGRATED_MODULES` + manifest +（若落盘）`storage.yml` | `audit_migration` 通过 |
| 7 | 自测：B5；主理人点验；回写 gaps 或清 gaps | 绿灯规则见 A10 |
| 8 | 进度：更新 `OPS-01-交接与进度.md` 必要段 | 不另建待办 md |

**停手**：无 Top3 文档、无主理人确认的 3 条独到处、文档非 `approved`。

模板：`docs/research/_TEMPLATE-top3.md`。排期真相：`docs/PROD-01-功能清单与优先级.md`。

## B2. 新增控件

1. 在 `widgets/` 实现  
2. 将选择器写入主题/QSS 生成管线  
3. 在 `modules/gallery` 展示全状态  
4. 加入 `CONTROL_CLASSES`  
5. 业务页方可引用  

## B3. 改主题 / 改色

1. 只改 `config/themes/<id>.json` 的 `palette`（或 typography）  
2. `python scripts/gen_qss_from_theme.py`  
3. 提交生成后的 `resources/qss/`  
4. 打开 gallery / 主路径目测主色、选中行、语义色  

## B4. 模块登记检查表

- [ ] `modules/<id>/`（`BasePage`）  
- [ ] `config/app.yml` 或用户 `menu.yml` 的 `menu_items`  
- [ ] `module_loader` / `MIGRATED_MODULES` 可 import  
- [ ] `config/migration_manifest.yml`（status + gaps）  
- [ ] 有落盘 → `config/storage.yml`  
- [ ] `python scripts/audit_migration.py`  

## B5. 自测、联调、验收

1. （建议）skill `toa3-sop-quality-pipeline` 产出用例地图；**禁止**把 Excel 用例库写入 `docs/`  
2. 必跑：`python scripts/verify_all.py`（`steps` 列表为门禁真相源；改门禁只改该文件）  
3. 启动：`python -m app.main`；Windows 强杀退出码 `4294967295` 可忽略  
4. 主理人点验 → 写入或清空该模块 `gaps`  
5. 闪退 / WebEngine：SOP-05 / skill `toa3-sop-debug-crash`  
6. 合入超边：`docs/architecture/ARCH-03-超边门禁.md`  

未列入 `verify_all.steps` 的 `verify_*.py` 为可选专项，不挡默认绿灯。

## B6. 打包发版

1. 确认 `APP_VERSION`；配置干净（shipped_config）  
2. 跑 `verify_all`（或至少 mvp + 护栏）  
3. `python packaging/build_windows.py`（及 Inno）  
4. `release_config_guard` / secrets 审计通过  
5. 需要时 `scripts/sync_release_version.py`  
6. 若涉及 DMS 仅更新下载说明：只建 draft，**人审后**再部署（见工作区 `dms-release-deploy.mdc`）  

细则：`docs/规范/SOP-04-打包发版.md`

## B7. 文档与协作回写

| 意图 | 只改 |
|------|------|
| 工程条款 / 本流程 | 本文（STD-01） |
| 架构裁定 | `docs/architecture/ARCH-*.md` |
| 排期 | `docs/PROD-01-功能清单与优先级.md` |
| 进度 | `docs/handoff/OPS-01-交接与进度.md` |
| 产品话术 | `docs/PROD-02-商务产品手册.md` / `config/product.yml` |
| 模块灯色 | `config/migration_manifest.yml` |
| 人机协作板说明 | `docs/handoff/OPS-02-协作任务说明.md` |

细则：`docs/规范/SOP-07-文档与进度回写.md`

## B8. 用户扩展（沙箱）

入口：顶栏 **系统 → 扩展**。只改 `data/user/extensions/<id>/`；禁止改宿主。  
SOP：`docs/规范/SOP-06-用户扩展开发.md` · Skill：`toa3-sop-user-extension` · 契约：`ARCH-07` + 扩展内 `HOST_API.md`。

---

# C. 附录 · 一页检索

| 主题 | 标准节 | 流程/SOP |
|------|--------|----------|
| 编码/分层 | A1 | — |
| UI/色/控件/密度 | A3 | B2 B3 · SOP-02 |
| 壳与介入 | A2 | ARCH-02 |
| 性能/生命周期 | A4 | — |
| 本机数据 | A5 | B4 · SOP-03 |
| 接口/密钥 | A6 | ARCH-04 |
| 需求/Top3 | A10.2 | B1 · SOP-01 |
| 测试验收 | A10.1 | B5 · SOP-03 |
| 打包 | A8 | B6 · SOP-04 |
| 授权/SKU | A9 | ARCH-04 |
| 闪退排查 | A4.6 | SOP-05 |
| 用户扩展 | — | B8 · SOP-06 |

规范清单：`docs/规范/00-规范清单.md` · 文档总目录：`docs/README.md`。