# ARCH-11 · 全局介入与热键配置点

> 系统介入五层定义见 [ARCH-02](ARCH-02-办公套件壳层.md) §3。  
> **机读档案**：`services/global_shell_features.py`（`GLOBAL_FEATURES`）。  
> **验证**：`python scripts/verify_global_shell.py`（已挂 `verify_all`）。  
> 更新：2026-09-14

---

## 1. 目的

把「双击 Ctrl 唤起、截图热键、拖入打开桌面、沉浸全屏、退出/托盘」等**全局壳能力**收成：

1. 可配置点（`config/app.yml` → `hotkeys`）  
2. 可验证档案（脚本门禁）  
3. Win / Mac 适配对照（Mac 未实现，口径先钉死）

禁止再在业务页写死第二套全局键。

---

## 2. 配置点一览（真相源）

| id | 用户能力 | 主要配置键 | 设置页 |
|----|----------|------------|--------|
| `double_ctrl_summon` | 双击 Ctrl 唤起 | `enable_global_toggle` · `toggle_window` · `summon_module_id` | 热键 |
| `screenshot_hotkeys` | 区域/全屏截图 | `enable_screenshot` · `screenshot` · `screenshot_region` | 热键 |
| `module_summon_hotkeys` | 模块唤起 | `module_shortcuts` + legacy `open_*` | 热键 |
| `immersive_fullscreen` | 沉浸全屏 | `toggle_fullscreen` · `enable_immersive_hotkey` | 热键 |
| `app_exit_restart` | 退出 / 重启 | `exit_app` · `restart_app` | 热键 |
| `close_to_tray` | 关窗进托盘 | `close_to_background` | 热键 |
| `drop_open_desktop` | 拖入文件→桌面浏览 | `enable_drop_open_desktop` | 热键 |
| `tray_menu` | 托盘模块 | `tray_modules` | （托盘列表，热键区关联） |
| `command_palette` | Ctrl+K | 暂固定（P2 纳入 yaml） | — |

用户覆盖：`data/user` 经 `save_hotkeys_config`；正式包与开发版隔离见 `edition_isolation`（并存时**开发版优先**占全局键）。

---

## 3. 代码锚点

| 能力 | 路径 |
|------|------|
| 档案表 | `services/global_shell_features.py` |
| OS 全局 RegisterHotKey | `services/hotkey_service.py` · `services/global_hotkey_bindings.py` |
| 双击 Ctrl | `services/double_ctrl_summon.py` |
| 窗内 ApplicationShortcut | `app/shell.py` `_register_hotkeys` |
| 拖入打开桌面 | `app/shell.py` `open_drop_paths` / `dropEvent` |
| 设置 UI | `modules/system_settings/hotkeys_section.py` |
| 托盘 | `services/tray_service.py` · `platform_experience` |

---

## 4. Mac 适配口径（未实现）

| Win | Mac 目标 |
|-----|----------|
| `RegisterHotKey` | 统一 `GlobalHotkeyBackend` 接口；Cocoa / 辅助功能权限文案 |
| `Double+Ctrl` LL hook | 双击 ⌘（可配）；禁止照搬 WH_KEYBOARD_LL |
| `F11` 沉浸 | 默认 `⌃⌘F`；仅前台 |
| `Ctrl+Q` 退出 | `⌘Q` |
| 系统托盘 | 菜单栏 `NSStatusItem` |
| 拖入文件 | Qt 已跨平台；保持 `enable_drop_open_desktop` |

实现时：业务只读 `hotkeys` 配置，**禁止** `#ifdef` 散落 modules。

---

## 5. 验证与发版

```powershell
python scripts/verify_global_shell.py
python scripts/verify_all.py   # 已包含上一行
```

发版说明须点名本版改动的全局能力（见 SOP-04 §2.1 发版说明模板）。
