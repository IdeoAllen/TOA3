# 10 · 必备能力与 Portal 评估

> 基于 TOA2 生产现状与 DMS 后端能力盘点（2026-08）。**TOA3 实施顺序以本表为准。**

## 1. 必备能力矩阵

| 能力 | TOA2 位置 | TOA3 现状 | 优先级 |
|------|-----------|-----------|--------|
| DMS 授权 / license | `common/license_manager.py`, `common/dms_license_client.py`, `login_window.py` | `auth_service` 本地 stub | **P0** |
| 菜单功能门禁 | `common/access_control.py`, `requires_license` | 未 enforcement | **P0** |
| 运行时路径 / 用户目录 | `common/runtime_paths.py` | `resolve_path` 仅开发相对路径 | **P0** |
| 封板 / 单实例 | `edition_isolation.py`, Inno `AppMutex` | 缺失 | **P0** |
| 托盘 | `common/tray_icon.py` | 缺失 | **P0** |
| 全局热键 | `common/hotkey_manager.py` | 壳内快捷键 only | **P0** |
| 截图 | `common/wechat_screenshot.py` | 缺失 | **P0** |
| 打包 PyInstaller + Inno | `packaging-app/` | 仅文档 | **P0** |
| 版本单一来源 | `app.yml` + build 脚本 | `app/version.py` 与 yaml 漂移 | **P0** |
| 系统设置（完整） | `system_settings_page.py` | 仅主题 | **P1** |
| 业务模块迁移 | `modules/*` | 3 实装 + stub | **P1** |
| 邮件 / 导出 / OCR | `email_utils`, yaml 配置 | 配置拷贝无实现 | **P1** |
| DMS 发版配对 | `DMS/db/releases/*`, Login 下载链接 | 无 TOA3 安装包条目 | **P1** |
| 插件（LaMa 等） | `common/plugins.py` | 缺失 | **P1** |
| 应用内自动更新 | 无（手动安装包） | 无 | **P2** |
| Portal 远程菜单 | 无 API | 无 | **P2** |
| Portal 账号统一 | DMS 用户 ≠ TOA 用户 | 无 | **P2** |

## 2. P0 落地顺序（建议）

1. 移植 `license_manager` + `dms_license_client` → `services/license/`
2. `runtime_paths` + 单实例 + edition isolation
3. 托盘 / 全局热键 / 截图（Qt + Win32）
4. `packaging/` PyInstaller + Inno，`3.0.0` 对齐
5. 导航 `access_control` 与 license `features` 联动

## 3. Portal 作用评估

### DMS Portal 今天实际承担什么

| 能力 | 是否已有 | 说明 |
|------|----------|------|
| TOA 授权码管理 | ✅（过渡） | DMS `AdminToaLicense` — **迁出至 TOA License 服务**；非 DMS 产品能力 |
| 安装包下载入口 | ✅ | Login 页链到 `yczh.tech/downloads/TOA-Setup-*.exe` |
| DMS 自身发版 | ✅ | AdminReleases + `deploy.ps1` |
| 交付系统 Web 账号 | ✅ | UserManage（助教/供应商 Web，**不是** TOA 桌面账号） |
| TOA 菜单远程下发 | ❌ | 无 API |
| TOA 桌面账号统一 | ❌ | TOA 用 license code，非 DMS 密码登录 |

### 方案对比

#### A. Portal 统一管理菜单 + 账号

- 优点：集中 RBAC、可远程关停功能
- 缺点：需新建菜单 API；桌面离线弱；与 license code 体系重复；启动依赖 DMS 可用性

#### B. 本地 `app.yml` 菜单 + DMS license 账本（TOA2 模型）**← 推荐**

- 优点：已生产验证；离线宽限期可用；`AdminToaLicense` 与终端 sync 已完备
- 缺点：菜单变更需发版或改配置；`features` 与 `menu_items` 两处要一致

### 结论（TOA3 v1 → 双产品 v2）

1. **DMS**：免费交付 Web；账号/RBAC 仅服务 DMS；**不按模块收费**；与 TOA **无强绑定**。
2. **TOA 账号**：license code + 本地 `license.json`；联网校验目标为 **TOA License 服务**（非 DMS）。DMS `AdminToaLicense` 为过渡/internal，非产品架构。
3. **TOA 菜单**：`config/app.yml` + license `features` / `feature_packs` 门禁。
4. **Portal**：TOA 下载 + 购买说明 + 链 DMS/TOA 入口；**不**统一账号/菜单。
5. **P2 可选**：只读 menu manifest；DMS 发码页外链 TOA 运营台。
6. **WCS 退役**：见 [15-WCS退役与平台收敛规划](15-WCS退役与平台收敛规划.md)。
7. **TOA 单机/联网/SKU**：见 [16-TOA授权与单机联网模式规划](16-TOA授权与单机联网模式规划.md)。

## 4. 与 DMS 发版流程关系

- DMS 后端/前端发版：遵守工作区 `dms-release-deploy.mdc`（draft → 人审 → deploy）。
- TOA3 安装包发版：独立 Inno 构建；在 DMS release SQL/说明中更新下载链接与版本号。
- **禁止** Agent 自批 DMS release 或直接 scp 生产。

## 5. 规则索引

项目级约束见 `.cursor/rules/toa3-*.mdc`，开发与 Agent 须遵守。
