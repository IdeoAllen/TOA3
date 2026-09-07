# ARCH-02 · 办公套件壳层与系统介入

> 主理人裁定：办公室人员安装 TOA3 = 集成剪贴板、截图、目录、文件、桌面、业务等常用办公效率工具。  
> Agent 规则：`.cursor/rules/toa3-office-suite-shell.mdc`  
> 文案同源：`config/product.yml` → `vision`  
> 更新：2026-09-07（域 Tab **已落地**，非目标态）

---

## 1. 产品定位

### 1.1 一句话

**装一个 TOA3，等于装齐日常办公效率工具箱**——对标头部、一站集成、键位跟手。

### 1.2 能力地图

| 用户心智 | 独立软件类比 | TOA3 落点 | 介入方式 |
|----------|--------------|-----------|----------|
| 剪贴板增强 | ClipX / Ditto | `clipboard_history` | 全局热键 popup + 后台捕获 |
| 截图标注 | 微信 / Snipaste | `screenshot_tool` + overlay | 全局热键全屏覆盖 |
| 快速记事 | 系统便笺 | `quick_notepad` | 热键唤起主窗 |
| 文件桌面 | 资源管理器增强 | `column_preview` | 壳内模块 + 预览 |
| 目录/交付 | 自建脚本 | `directory_*` | 壳内向导 |
| 文件批处理 | 小工具合集 | `batch_rename` 等 | 壳内模块 |
| 培训业务 | 表格/模板/日程 | `business` 组 | 壳内模块 |

### 1.3 集成标准

- 高频刚需做强；每项对标品类 Top3。  
- 同类能力不输独立 App **主路径**。  
- 本地优先；输出经 `storage_paths`。

---

## 2. 壳层信息架构（现行）

### 2.0 术语

| 层级 | 用户称谓 | 技术键 | 位置 |
|------|----------|--------|------|
| 一级 | **子模块**（子系统） | `group_id` | 顶栏 Tab |
| 二级 | **功能模块** | `menu_items[].id` | 侧栏 |
| 三级 | **任务页** | `BasePage` | 主内容区 |

代码：`GROUP_ORDER` / `MainShell.select_domain` / `rebuild_nav`。

### 2.1 布局

```
┌─ ShellHeader ─────────────────────────────────────────────┐
│ Logo  品牌名                    用户 主题 设置 关于 …      │
├─ ShellSubHeader（一级 · 子模块 Tab）──────────────────────┤
│ [首页] [办公] [图片] [文件] [引擎] [业务] [系统]            │
├──────────┬────────────────────────────────────────────────┤
│ 侧栏     │ ModuleHost（BasePage · 懒加载）                  │
│ （当前子 │                                                 │
│ 系统功能）│                                                 │
├──────────┴────────────────────────────────────────────────┤
│ StatusBar                                                 │
└───────────────────────────────────────────────────────────┘
```

**已废弃**：快捷条依赖「模块」下拉才能发现功能（不得再写回）。

### 2.2 一级 · 顶栏子模块

| group_id | 顶栏 | 侧栏完整名 | 内容 |
|----------|------|------------|------|
| `home` | 首页 | 首页与桌面 | 首页、桌面浏览 |
| `office` | 办公 | 日常办公 | 剪贴板→截图→记事→任务→大模型→网页 |
| `image` | 图片 | 图片处理 | 去水印、媒体工坊、扫描件、提取等 |
| `files` | 文件 | 文件与目录 | 建夹→透视→重命名→PDF→打包→合成 |
| `engines` | 引擎 | 开源引擎 | Harness、OpenPencil、Draw.io、ComfyUI 等 |
| `business` | 业务 | 培训业务 | 排课→材料→检核→交付 |
| `system` | 系统 | 系统 | 设置、扩展、控件库 |

- 数据源：`menu_registry.GROUP_ORDER` + `GROUP_LABELS`，与 `product.yml` `module_groups` 一致。  
- 单击子模块 Tab → `select_domain` → 侧栏只显示该子系统功能模块。  
- 兼容旧组：`ai`→`engines`，`directory`/`file`→`files`。

### 2.3 二级 · 侧栏

- 只显示当前子模块下 `show: true` + manifest + license 允许的项。  
- 排序来自配置 `order`；禁止业务页硬编码列表。

### 2.4 三级 · 模块页

- `BasePage`；刷新放 `on_enter`（异步）；清理放 `on_leave`。  
- 业务页不得自建顶栏子模块或全局功能列表。

### 2.5 配置（P2 可选）

```yaml
# config/app.yml 可选扩展（未实现前勿擅自加字段）
shell:
  domain_shortcuts:
    office: [screenshot_tool, clipboard_history, quick_notepad]
```

`domain_bar` **已实现**（顶栏子模块 Tab）。子模块内 last_module 记忆、办公三钮快捷条 = **P2**。

---

## 3. 系统介入层

### 3.1 五层

| 层 | 说明 | 示例 |
|----|------|------|
| Ambient | 零 UI 后台 | 剪贴板 watcher |
| Summon | 唤起主窗/模块 | 热键、托盘、`_summon_module` |
| Overlay | 临时全屏/浮层 | 截图、剪贴板快贴 |
| Chain | 产出衔接 | 截图 → OCR |
| Palette | 命令面板 | Ctrl+K（roadmap / P2） |

### 3.2 代码锚点

| 能力 | 文件 |
|------|------|
| 壳 | `app/shell.py` |
| 热键 | `services/hotkey_service.py` + `app.yml` `hotkeys` |
| 托盘 | `services/tray_service.py` |
| 截图 | `services/screenshot_overlay.py` |
| 剪贴板 | `modules/clipboard_history/` |

### 3.3 铁律

1. 全局介入可关（`hotkeys: none`）。  
2. Overlay 必须 Esc/完成可退。  
3. 热键路径禁止同步长联网。  
4. Wave★：壳内可发现 + 热键/托盘/Overlay 至少一种。  
5. 最终 `navigate(module_id)`，id 必须在 `menu_items`。

---

## 4. 路线图状态

| 阶段 | 内容 | 状态 |
|------|------|------|
| R0 旧侧栏全展开 + 模块下拉 | 历史 | **已废** |
| R1 文档/规则/product 口径 | — | **已落地** |
| R2 子模块 Tab + 侧栏过滤 | `select_domain` | **已落地** |
| R3 办公顶栏三钮快捷 | SubHeader | P2 |
| R4 Ctrl+K 命令面板 | menu 同源 | P2 |
| R5 链式 UI 提示 | 截图/OCR | 按 gaps |

---

## 5. 相关文档

| 文档 | 关系 |
|------|------|
| [01-平台基础](ARCH-01-平台基础.md) | 分层、登记、授权摘要 |
| [16-TOA授权…](ARCH-04-授权与单机联网.md) | 菜单不走 Portal 下发 |
| `docs/PROD-01-功能清单与优先级.md` | Wave★ |
| `docs/规范/STD-01-工程标准与流程.md` | 工程门禁 |

---

## 6. 待主理人点验（非阻塞已落地项）

- [ ] 七个子模块命名对用户是否最终定稿  
- [ ] 「安装=工具箱」是否写入关于/安装页文案  
- [ ] 是否做 R3 办公三钮 / R4 Ctrl+K  
- [ ] P2：资源管理器「发送到 TOA」  
