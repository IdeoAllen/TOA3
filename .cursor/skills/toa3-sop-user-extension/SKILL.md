---
name: toa3-sop-user-extension
description: >-
  在 TOA「系统 → 扩展」用名称 + 需求描述创建功能并挂到「业务」；沙箱隔离，可移除，不改智能体与宿主。
  Use when the user says 帮我做一个/加个功能/扩展/放到业务/去做扩展/系统自我进化,
  or wants a custom side-nav tool without touching official modules.
---

# TOA3 · 扩展（系统自我进化 · 业务板块）

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

面向岗位用户：写清 **名称 + 需求**（场景 / 痛点 / 作用）→ 出现在顶栏 **业务**。  
**主入口（用户可见）**：顶栏 **系统 → 扩展 → 自定义插件**（增长中心 · `user_extensions`）。  

闭环：填名称与需求 →「创建并去开发」→ 目录 + `REQUIREMENTS.md` + AGENTS → 工作区 → **自动投喂** →「开发完成」→ 打开 →「移除」。  
也可「导出包 / 导入包」（本机 zip，doc 29b）。

**不是**官方新功能流程（那个用 `toa3-sop-new-feature`）。  
**不要**再让用户去改「一句话扩展」占位脚本或二次编辑超长提示词后再发送。

## 铁律

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

1. **只写** `data/user/extensions/<id>/`  
2. **禁止**改 `app/`、`services/`、官方 `modules/`、`config/`、QSS、安装目录  
3. **禁止研究宿主**：不要为「搞懂加载」去读 `plugin_loader` / `harness_*` / `widgets/__init__.py`；约定写在扩展内 `AGENTS.md` + `HOST_API.md`  
4. **禁止**影响智能体安装、其它软件、系统目录  
5. 默认 `group = business`；可 **移除**（取消登记 + 删目录）  
6. 对用户白话报错，禁止堆栈糊脸  
7. **只做业务主路径**：少分析、快交付；导入推荐**单文件入口页**  
8. **界面必须用控件库排版**：`ScrollPage` + `PageHeader` + `FormSection`；…（**surface=qt**）  
8b. **网页面（surface=webview）**：只改 `ui/` HTML/JS；用 `TOA.ready` + `toa.*` 桥（见 HOST_API.md）  
9. **创建必填需求描述**：…

## Cursor / Harness 怎么用本 skill

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

| 角色 | 做什么 |
|------|--------|
| 用户 | **系统 → 扩展** 填名称 + 需求 →「创建并去开发」；不要在智能体里改占位 CLI |
| Cursor（你） | 用户一句话要功能时：引导去扩展页填写，或直接改扩展目录；**不要**让智能体去翻宿主 |
| Harness 投喂 | `build_dev_task_prompt` 已嵌入本 skill 红线 + 用户需求；`REQUIREMENTS.md` / `AGENTS.md` / `HOST_API.md` 为工作区说明书 |
| 快捷指令 | 「去做扩展」只引导去扩展页，不再塞可编辑脚本模板 |

投喂任务必须强调：

- 唯一目录 = 扩展绝对路径  
- 先读 `REQUIREMENTS.md` 再实现  
- 禁止 Grep/Read 宿主 `services/`、`app/`、`widgets/`、`core/`、官方 `modules/`  
- API 只查扩展内 `HOST_API.md`  
- 禁止 `from modules.<id>...`；逻辑写在入口页单文件  

## 流程

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

在 TOA：**系统 → 扩展 → 自定义插件** → 名称 + 需求描述 → **创建并去开发**。

或 CLI（开发自测）：

```powershell
python scripts/create_user_extension.py --name "请假台卡" --desc "场景：… 痛点：… 作用：…"
```

实现入口页 →（可选）`python scripts/audit_plugin.py <root>` → 告诉用户：

> 做好了。打开 TOA → 顶栏 **系统 → 扩展** → 选中 → **开发完成** → **打开**（顶栏业务）。不要了点 **移除**。

## 边界

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

| | 扩展（本 skill） | 官方模块 | Harness |
|--|------------------|----------|---------|
| 是什么 | 用户岗位插件 | 发版内置 | 编码智能体（只当施工队） |
| 入口 | 系统 → 扩展 | 侧栏菜单 | 智能体页 |
| 可移除 | 是 | 否 | 不管业务卸载 |
| 可写范围 | 仅扩展目录 | 全仓发版流程 | **仅**当前扩展工作区 |
| 打包销售 | `feature_id=user_extensions` | 各模块 feature | `harness_agent` |

## 参考

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

- `docs/architecture/ARCH-07-用户扩展范式.md`（扩展全册，含原 28b/c/d 附册）
- `services/extension_lifecycle.py`（`build_dev_task_prompt`）
- `services/extension_guard.py`（完成时体检）
- `services/plugin_scaffold.py`（`AGENTS.md` / `REQUIREMENTS.md` 模板）
- `modules/user_extensions/`（系统侧栏入口）
