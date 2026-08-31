# 25 · 扩展 · 需求围挡（Figma Brief · 系统设置入口）

> **状态**：与实现对齐 · 2026-08-29  
> **工程**：`modules/system_settings/extensions_section.py` · 架构 28  
> **入口**：**系统设置 → 扩展**（Harness 仅作开发能力，不作管理入口）

## 产品叙事（FDB）

```text
办公套件集成 → 业务能力 → 本机扩展（自我进化）
         ↓
真正效率工具 → 岗位与团队角色升级（为 FDB 而生）
```

Harness = 能力接入里的强智能体；扩展 = 用户可添加/移除的岗位插件。

## 界面（专业干净）

| 区域 | 内容 |
|------|------|
| 提示条 | 一句：扩展让本机 TOA 按岗位进化；可随时移除 |
| 添加 | 名称 +「添加」 |
| 已安装 | 表：名称 \| 状态（业务侧栏 / 已隐藏 / 未启用） |
| 操作 | 打开 · 开发 · 隐藏 · 移除 · 文件夹 |

**禁止**：Harness 工具栏第二入口、弹窗堆满按钮、「刷新上架」中间态。

## 工程对照

| UI | 代码 |
|----|------|
| 设置页签 | `config/app.yml` `settings_menu` · key=`extensions` |
| 面板 | `ExtensionsSection` |
| 移除 | `services.plugin_registry.remove_plugin` |
| 跳转兼容 | `open_extension_hub` → `open_tab("extensions")` |
