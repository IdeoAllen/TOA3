# Harness 嵌入与壳层结合

> 编码智能体 · `harness_agent` · 与 `docs/research/harness_agent-top3.md` 配套

## 1. 一句话

**Guest = 正版 DeepSeek Harness Web（同一 URL）；Host = TOA 原生壳（启停、办公链、只读侧栏）。**  
用户感到「一个整体」，是因为外框、工具栏、侧栏都是 TOA 控件库；中间干活区仍是 Harness 官方界面，不是山寨聊天页。

## 2. 双表面（同一 Sidecar）

| 表面 | 实现 | 数据 |
|------|------|------|
| **内嵌** | `QWebEngineView` → `http://127.0.0.1:{web_port}` | 与浏览器共用 `DSH_HOME`、同一 dsh 进程 |
| **系统浏览器** | `webbrowser.open(web_url())` | 会话/工作区仍在 Harness 内，不另开「TOA 版」 |

切换规则：

- 默认 **内嵌**；用户可随时「浏览器打开」脱离，再点「显示内嵌」收回。
- 配置 `surface_mode: browser` 时，启动后优先打开浏览器，页内显示占位提示（Sidecar 仍由 TOA 托管）。
- **禁止**第二套 Web 地址或 TOA 自研 Agent 页替代 `dsh web`。

## 3. 布局（Host + Guest · v2）

```
┌─ 状态 + 主操作（启停/投喂/表面切换） ─────────────┐
├─ [仅首次] 单行引导 → 系统设置 ─────────────────────┤
├─ [有办公链时] 投喂条 ──────────────────────────────┤
├──────────────────────────────────────────────────┤
│           Harness 原版 Web（Guest · 全宽）          │
└──────────────────────────────────────────────────┘
```

- **不建**左会话索引、右用量仪表 — 与 Harness 内左侧栏/设置 **100% 重复**，已移除。
- 会话切换、工作区、插件、用量详单：**只在 Harness Web 内操作**。

## 4. TOA Host 能力清单（每项须能回答「为何不在 Harness 里做」）

| 能力 | TOA 独有价值 | 入口 |
|------|-------------|------|
| Sidecar 启停/重启 | 用户不开终端；与套件托盘/热键一体 | 主按钮 / 更多 |
| 内嵌 ↔ 浏览器 | 同一 DSH_HOME，随场景切换表面 | 工具栏 |
| 办公链投喂 | 剪贴板/OCR → Harness 输入（套件闭环） | 投喂条 / 投喂 |
| 导出最近会话 MD | 落盘 `output/`，培训留档可追溯 | 更多 |
| 首次环境引导 | 小白不进 Harness 也能完成 Node/Key | 首行横幅 → 设置 |
| 路径/密钥/端口 | 与全应用设置一致，不散落多处表单 | 系统设置 |

## 5. TOA 原生面 **禁止做**（山寨红线）

- 自研聊天/Agent 输入框作为主界面
- TOA 内 **dsh/Cordis** 插件安装器（须在 Harness / `dsh plugin` 或 Harness 设置）
- TOA 内工作区管理器（须在 Harness 左侧工作区）
- 把 Harness 插件误当成 TOA 侧栏模块（TOA **业务插件包**另见 `28-Harness驱动的业务插件开发范式.md`）
- 注入 CSS 改 Harness 主题（默认 `theme_harmonize: false`）
- 默认自动 JS 填输入框（默认 `feed_auto_inject: false`；以剪贴板为主）

## 6. 合格验收（结合得好）

1. 内嵌与浏览器打开 **同一 URL**，会话在 `DSH_HOME` 下连续。
2. 未启动时单行引导可完成配置；启动后 Harness Web 全宽。
3. 无 TOA 侧会话/用量重复 UI；会话与工作区仅在 Harness 内。
4. 剪贴板/OCR「送到智能体」→ 复制 + 进页，在 Harness 输入框粘贴（与浏览器版一致）。
5. `python scripts/audit_migration.py` 通过；无新增「替代 Harness 主路径」的菜单项。

## 7. 代码落点

| 层 | 路径 |
|----|------|
| 页面 Host | `modules/harness_agent/harness_agent_page.py` |
| Web 容器 | `modules/harness_agent/web_host.py` |
| 首次引导 | `modules/harness_agent/setup_gate.py` |
| 办公链条 | `modules/harness_agent/feed_strip.py` |
| 状态探测 | `services/harness_probe.py` |
| 导出 | `services/harness_export.py` |
| 一键安装 | `services/harness_setup.install_harness_runtime` |
| 双表面 | `services/harness_surface.py` |
| Sidecar | `services/harness_sidecar.py` |
| 配置 | `config/harness.yml` · `data/user/harness.yml` |
| UI 偏好 | `services/harness_ui_prefs.py` · `data/module/harness_agent/ui_prefs.json` |

## 8. 产品重构 v2（2026-08-27）

**结论**：左/右只读侧栏与 Harness 内 UI 重复，制造「眼花缭乱」且无独到处 → **整页移除**。

**§3.5 独到之处 #1 修订**：由「三栏指挥台」改为 **「套件内全宽 Harness + 零终端启停」** — 一体感来自同一安装包与办公链，而非复制 Harness 会话/用量 UI。

| 验收 | 标准 |
|------|------|
| 首屏 | 仅状态条 + Harness Web，无第三套会话列表 |
| 投喂 | 办公链进页出现可操作条，一键送入 Harness |
| 导出 | 更多 → 导出最近会话 → `show_saved` + output 目录 |
| 配置 | 未完成三步时单行引导，详表在系统设置 |

