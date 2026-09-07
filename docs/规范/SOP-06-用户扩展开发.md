# SOP-06 · 用户扩展开发

> **编号**：SOP-06 · **Skill**：`toa3-sop-user-extension`  
> **依据**：STD-01 · B8 · ARCH-07

## 1. 目的

在「系统 → 扩展」沙箱内为当前用户增加功能，不破坏宿主。

## 2. 硬边界

| 允许 | 禁止 |
|------|------|
| 只改 `data/user/extensions/<id>/` | 读改 `app/` `modules/` 官方 `config/` `widgets/` |
| 扩展内 `HOST_API.md` / `toa_bridge.js` | 全盘搜索、未声明联网/shell/注册表 |
| 登记 `data/user/plugins.yml` | `from modules.xxx` 加载官方模块路径 |

## 3. 步骤

1. 用户在扩展页描述需求  
2. Agent 只读扩展目录：`REQUIREMENTS` / `AGENTS` / `HOST_API` / 入口  
3. 实现主路径（webview 改 `ui/`；qt 面用 BasePage+widgets）  
4. 用户：开发完成 → 打开 → 顶栏业务可见  
5. 不需要：移除即可  

细则：Skill + ARCH-07。
