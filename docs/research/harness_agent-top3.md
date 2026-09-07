# Top3 对标分析 · `harness_agent` · 编码智能体（DeepSeek Harness）

> 状态：`shipped`（主理人 2026-08-27 验收通过 · migration_manifest `done`）
> 日期：2026-08-27
> 关联：`docs/PROD-01-功能清单与优先级.md` · AI 子模块
> 门禁：`.cursor/rules/toa3-feature-top3-research.mdc`

---

## 1. 用户场景（必填）

| 项 | 内容 |
|----|------|
| 谁 | 培训运营 / 开发者主理人，日常与 Codex、WorkBuddy 并列使用 Harness |
| 何时 | 写脚本、改业务页、处理办公素材、多轮 Agent 任务 |
| 输入 | 自然语言指令；剪贴板/截图 OCR 文本；本地项目目录 |
| 输出 | Harness 多轮会话、文件/终端产出；会话导出 Markdown |
| 失败体验 | 状态栏 + 设置指引；未安装 Node/dsh 时明确路径配置项 |

---

## 2. Top3 对标产品

| # | 产品 | 平台 | 为何入选 | 资料链接 |
|---|------|------|----------|----------|
| 1 | OpenAI Codex CLI | 桌面/IDE | 会话 resume、跟手键位、IDE 内 Agent 标杆 | https://github.com/openai/codex |
| 2 | WorkBuddy + dsh | Win | 本机 Sidecar、DSH_HOME 隔离、与 Harness 并存 | 本机 WorkBuddy 实践 |
| 3 | DeepSeek Harness Web | 桌面 Web | Agent 主路径、插件化 Harness、Web UI | https://github.com/deepseek-ai/deepseek-harness |

（可选）技术参考：`vendor/dshm`（MIT · 会话/用量只读管理终端）

---

## 3. 取长补短矩阵

| 维度 | Codex CLI | WorkBuddy+dsh | DSH Web | **TOA 采纳** |
|------|-----------|---------------|---------|--------------|
| 核心流程 | IDE/终端内 resume | Sidecar 启停 | 全功能 Agent | 三栏一体指挥台 + 嵌入 Web |
| 交互细节 | 会话列表 | 环境变量治理 | 侧边栏选会话 | 原生左/右栏 + 中栏 Web |
| 性能 | 快 | 本地 | 依赖 Node | 进页探活；Sidecar 异步启停 |
| 能力深度 | OpenAI 栈 | dsh 专用 | 插件生态 | 复用 dsh，不重写 Agent 环 |
| 短板避开 | 闭源、无办公链 | 独立 App | 无 TOA 主题/链 | 不做第二套 Agent 运行时 |

### 必学（至少 3 条）

1. 会话列表与 resume（Codex `resume` 心智）
2. Sidecar 零终端启停（WorkBuddy 脚本实践）
3. Harness Web 作为主干活区（不重写工具环）

### 明确不学 / 否决

1. 在 TOA3 内重写 Cordis 插件与 Agent 环
2. 双 Web 窗口（dsh + dshm 各一页）割裂方案
3. **自建 Harness 山寨 UI**（工作区/插件/费用/聊天等替代页 — 一律在正版 Harness Web 内完成）

---

## 3.5 三个独到之处（与主理人共创 · 门禁核心）

| # | 独到主张（一句话） | 用户可感知价值 | 可测验收 | 论证结论 |
|---|--------------------|----------------|----------|----------|
| 1 | **套件内全宽 Harness**：正版 Web 占满任务页；启停/投喂在薄 Host 条 | 不必另开浏览器也能干活；与办公模块同一壳 | 进页无左/右重复侧栏；中间 Web ≥90% 高 | ✅ 已确认（v2 修订） |
| 2 | **办公链投喂**：剪贴板/截图 OCR → 一键送入 Harness 新会话 | 少复制粘贴，套件内闭环 | 剪贴板或截图页点「送到智能体」，Harness 首条含该内容 | ✅ 已确认 |
| 3 | **Sidecar 零终端**：进页探活、工具栏启停、路径可配；关 TOA3 可选保活 | 与 Codex/WorkBuddy 并肩，无需开终端 | 未启动显示「启动」；5s 内 Web 可加载；设置可改路径 | ✅ 已确认 |

共创纪要：

- 用户明确：至少含启停；不接受两个割裂窗口；定位与 Codex/WorkBuddy 并肩。
- 新建 AI 顶栏子模块；`llm_assistant` 迁入同组。

- [x] **主理人已确认以上恰好 3 条**（日期：2026-08-27  确认方式：集成规划对话）

---

## 4. 技术方案（过门才写码）

| 项 | 结论 |
|----|------|
| 选定栈 / 库 | PySide6 + QWebEngineView；Node `@deepseek-ai/dsh` Sidecar；`vendor/dshm` 只读 JSON |
| 否决项及原因 | 不走 `integrations` HTTP；不打包 Node；不重写 Harness UI |
| 架构落点 | `modules/harness_agent/` · `services/harness_sidecar.py` · `services/harness_store.py` · `config/harness.yml` |
| 性能约束 | 进页 health probe 异步；禁 UI 线程阻塞启停；dshm 子进程取 JSON |
| 品质验收 | 启停；三栏；导出 `show_saved`；热键 Summon；投喂链 |
| 如何兑现 §3.5 | 三栏页；clipboard/screenshot 链；sidecar + 设置页 Harness 区 |

**resume 策略**：dsh 无 CLI `--resume` → 左栏复制 `dsh-session:` URI + 状态栏指引打开 Harness 侧边栏对应会话。

---

## 5. 签字栏

- [x] Top3 已检索并填表
- [x] 取长补短结论可执行
- [x] **§3.5 三独到处已经主理人论证确认**
- [x] 验收标准可测
- [x] **approved** — 允许进入实现
