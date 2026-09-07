# ARCH-01 · 平台基础（现行）

> 更新：2026-09-07。日常工程门禁以 `docs/规范/STD-01-工程标准与流程.md` 为准；本文只写**现行架构真相**。  
> 旧「原 01–11 合订博物馆稿」已进 `docs/_archive/architecture/`，勿再当门禁。

---

## 1. 产品与双线

| 项目 | 路径 | 技术栈 | 状态 |
|------|------|--------|------|
| TOA2 | `../TOA` | tkinter | **封板**，只读逻辑 |
| TOA3 | 本仓库 | PySide6 | **主开发线** |

**定位**：办公室人员安装 TOA3 = 集成常用办公效率工具（剪贴板、截图、记事、任务、图片、文件、引擎等）+ 可选培训业务。叙事见 `docs/PROD-02-商务产品手册.md`；首页/关于文案见 `config/product.yml`。

**授权**：TOA License 云服务（`https://toa-service.yczh.tech`），与 DMS **无运行时绑定**。详见 [16-TOA授权与单机联网模式规划](ARCH-04-授权与单机联网.md)。

---

## 2. 分层依赖（只允许向下）

```
modules/*                 业务页（BasePage）
    ↓
widgets/* + ui/*.ui       控件与 Designer
    ↓
app/shell.py · theme_loader · core/* · app/module_loader
    ↓
services/*                无 UI 能力（存储、热键、integrations、license…）
    ↓
config/* · resources/qss  配置与生成后的皮肤
```

禁止：业务页 `setStyleSheet`、硬编码色、裸 `QPushButton` 作主按钮、在 `modules/` 另建控件库、用 `QTabWidget` 作模块外壳。

主题：`config/themes/<id>.json` → `scripts/gen_qss_from_theme.py` → `resources/qss/` → `app/theme_loader.apply_theme`。

---

## 3. 壳与导航（现行）

| 层级 | 用户称谓 | 代码 | 位置 |
|------|----------|------|------|
| 一级 | 子模块 / 子系统 | `group_id` · `MainShell.select_domain` | 顶栏 Tab（`ShellSubHeader`） |
| 二级 | 功能模块 | `menu_items[].id` · `navigate` | 侧栏（按当前子模块过滤） |
| 三级 | 任务页 | `BasePage` · 懒加载 | 主区 `QStackedWidget` |

- 菜单只来自 `config/app.yml` / `data/user/menu.yml` + `services/menu_registry`；**禁止**业务页写死工具列表。  
- 系统介入（热键/托盘/覆盖层）：见 [12-办公套件壳层与系统介入](ARCH-02-办公套件壳层.md)。  
- 主窗与子窗隔离：见 [31-主子窗隔离](ARCH-08-主子窗隔离.md)。

---

## 4. 模块登记与加载（现行）

新模块须齐：

1. `modules/<id>/` 页面（`BasePage`）  
2. `config/app.yml`（或用户 `menu.yml`）`menu_items`  
3. `app/module_loader.py` / `MIGRATED_MODULES` 可 import  
4. `config/migration_manifest.yml`（status + gaps）  
5. 有落盘则 `config/storage.yml`  
6. `python scripts/audit_migration.py`  

加载链：`menu_registry` 可见项 → 壳 `navigate(module_id)` → `module_loader` 实例化 → `on_enter`。  
完成灯：`done` 仅当 gaps 空且主理人认可；侧栏尊重 `show` + manifest + license。

---

## 5. 配置、存储、密钥

| 项 | 真相 |
|----|------|
| 环境 | `TOA_ENV`：`development` / `release`；release **不**加载 `app.dev.yml` |
| 用户写回 | 只写 `writable_config_path()` / `data/user/*.yml`；勿整文件覆盖仓库带注释 yaml |
| 模块数据 | `module_data_dir` / `module_output_dir`（`services/storage_paths`） |
| 开发 vs 正式 | 开发可用仓库 `data/`；正式版在用户目录（如 `%LOCALAPPDATA%\YCZH-TOA3`）；**不共用** |
| 密钥双轨 | LLM 等 → `data/user/integrations_secrets.json`；Harness → DSH credentials；**禁止**写进 `config/*.yml` |
| 外部 HTTP | 只经 `services.integrations.get_client` |

细则：`docs/规范/STD-01-工程标准与流程.md` §7–8。

---

## 6. 授权与 Portal（摘要）

| 领域 | 主数据 |
|------|--------|
| TOA 桌面授权 | license code + 本机 `license.json`；入口 `services/license_client.py`（包装历史实现） |
| 可售方案 | `config/feature_packs.yml`：`tiyan`（全功能方案）；`local_free` 为单机免费层 |
| 菜单 | 本机 yaml；Portal **无**远程菜单下发 |
| DMS | 独立免费 Web；**不是** TOA 账本 |

---

## 7. 引擎与扩展（指针）

| 专题 | 文档 |
|------|------|
| Harness / 本地 Web 引擎 | [18-引擎与Harness](ARCH-05-引擎与Harness.md)（默认 **浏览器** 表面） |
| 生命周期 Host / 费用不做 | [33-桌面端职能规划-网页主力之外](ARCH-09-桌面端职能.md) |
| 用户扩展 | [28-Harness驱动的业务插件开发范式](ARCH-07-用户扩展范式.md) |
| 合入自检 | [14-超边门禁与目标锁定](ARCH-03-超边门禁.md) |

`engine_host_hub`：**Hold**，菜单隐藏。

---

## 8. 测试与打包（已落地）

| 项 | 入口 |
|----|------|
| 门禁全集 | `scripts/verify_all.py`（steps 为真相源） |
| 版本号 | `app/version.py` → `APP_VERSION` |
| 打包 | `packaging/build_windows.py` + Inno；`shipped_config`；禁打 `data/user` / secrets / `license.json` / `app.dev.yml` |

完整条款：`docs/规范/STD-01-工程标准与流程.md` §10–13。

---

## 9. 产品核心（八条 + 办公套件）

1. 风格统一（QSS + widgets）  
2. 简捷实用（单主任务、小白默认可用）  
3. 分层可扩展  
4. 安全可靠（license、无 skip_login 生产包）  
5. 三方统一 integrations  
6. 异常与窗口统一（`show_saved` 生成完成）  
7. Top3 + 三独到处经主理人确认  
8. 验收不回退（manifest gaps）  
9. 办公套件一体 + 壳三级导航 + 系统介入双轨 + 双门槛引导  

Cursor 规则：`.cursor/rules/toa3-*.mdc`；与本文冲突时以 **代码 + `工程标准` + 规则** 为准。
