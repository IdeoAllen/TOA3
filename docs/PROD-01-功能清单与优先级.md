# TOA3 功能清单 · 场景 · 优先级 · 做强原则

> 版本：2026-09-02 · 产品：运营宝 TOA3  
> 模块灯色与 gaps 写在 `config/migration_manifest.yml`；当前迭代进度写在 `docs/handoff/OPS-01-交接与进度.md`。  
> **铁律：不做功能凑数。每个功能开发前必须全网检索评估技术方案，目标做成该场景下能力最强的实现。**

---

## 0. 开发总则（先于一切功能）

| 规则 | 说明 |
|------|------|
| **先评估再动手** | 开做前检索：同类桌面工具、开源库、行业最佳实践；输出「方案对比表」写入该模块 `docs/` 或 PR 说明 |
| **做强不做全** | 宁可少做几个功能，也要把已做功能做到体验与能力对标头部产品 |
| **菜单可维护** | 入口一律 `menu.menu_items` / `data/user/menu.yml`；禁止代码写死入口列表 |
| **控件库唯一** | UI 只用 `widgets/` + 主题预览对照；例外需注释 |
| **能力外挂** | OCR / LLM / 翻译 / AI 修复走 `services/integrations`，密钥存本机 secrets |
| **对照 TOA2** | 业务默认行为与 TOA2 核心能力对齐；UI 用 TOA3 壳 |
| **个人高频优先** | Wave★ 仍优先保障；其它需求 **直接并行开发**（STD-01 A0.8 · B9） |
| **亮点研究** | **可选补强**，不挡写码（2026-09-14） |
| **并行直开** | 无 WIP/approved 开工上限；统筹管合入与 **A10.4 发版** |

### 优先级定义

| 级 | 含义 | 开做条件 |
|----|------|----------|
| **P0★** | 个人最高频 | 立刻开做；并行时优先保障可点验 |
| **P0** | 高频刚需 / 底座 | 直接开轨并行 |
| **P1** | 增强 / 培训主链路 | 直接开轨并行 |
| **P2** | 低频 | 有压强即开 |
| **Hold** | 暂不投入 | 不擅自开（除非主理人改 Hold） |

### 状态

`done` 核心已对齐 · `mvp` 能用但未做强 · `stub` 仅占位 · `missing` 清单有、产品尚无 · `research` 评估中未写码

---

## 0.5 个人最高频八件套（开发真相源 · 优先于一切业务波次）

> 来源：产品主理人自述日常最高频。**先把这 8 个做到「个人愿意每天用」的强度，再扩培训与其它白领工具。**

| 序 | ID | 名称 | 应用场景 | 最强能力目标 | 现状 | 下一步 |
|----|-----|------|----------|--------------|------|--------|
| 1 | `screenshot_tool` | 截图 | 会议/反馈/发图；一切屏幕捕获入口 | 对标 Snipaste：多屏、S 重切、标注不糊、历史复用、热键稳、托盘唤起 | mvp | **Wave★-1** 评估后继续打磨 |
| 2 | `clipboard_history` | 剪贴板 | 反复粘贴文案/图；跨窗口搬运 | 对标 Ditto：文本+图、搜索、隐私、热键唤起、持久可靠 | mvp | **Wave★-2** |
| 3 | `quick_notepad` | 记事本 | 会中速记、草稿 | 见 **§0.5.1**（编辑/源码/预览；组件库=标记全集） | mvp | **Wave★-3** 点验 |
| 4 | `quadrant_tasks` | 任务管理 | 状态看板 · 日历排期 · 四象限优先级 | 进度蓝/橙/绿；优先级红立刻/蓝计划/橙速办/灰延后；任务说明+记事本传送；模式顺序状态→日历→四象限 | **mvp** | **Wave★-4** 点验后清 gaps |
| 5 | `watermark_remover` | 去水印 | 擦除豆包/角标/特殊照片水印 | **本地默认可完成**：轻量修复开箱即用；AI/LaMa **可选增强**（勾选才走），失败自动回退；框选+涂抹+自动角标 | mvp | **Wave★-5** |
| 6 | `image_watermark` | （日常通用加水印） | — | **侧栏默认隐藏**（主理人 2026-08-26）：TOA 加水印以业务 `watermark_photo_generator` 为准，勿与班级规则水印并列三入口 | mvp·隐藏 | 原 Wave★-6，已降级 |
| 7 | `directory_generator` | 快速创建多文件夹 | 一次建一批目录树（班级/项目/归档） | 粘贴名单即建；模板；预览；幂等；失败可续 | **done** | **Wave★-7** 已点验；Wave F 可开 |
| 8 | `screenshot_translate` | 截图翻译 | 框选屏幕 → 识字 → 译文（对照/替换） | 热键框选；原文+译文并列；可换引擎；可拷贝；延迟低 | **mvp** | 挂截图工具栏；**点验后收口**；勿独立菜单 |

### 0.5.1 快速记事 · 产品模型（一源 · 编辑 / 源码 / 预览）

> 真相源：本小节。运行时短承诺：`config/product.yml`。对外话术：`docs/PROD-02` §6.2。  
> **2026-09-30 主理人**：借鉴 WPS 的 Markdown 写作能力，补 **源码面**、**效率指南**、**导入 / 拖入 .md**。  
> **编辑 = 所见即所得**（打开就像成品文档）；**源码 = 直接改 Markdown**；**预览 = 只读纸面**。三面同一份正文。  
> **落盘真源仍是单一 Markdown**（禁止 HTML 真源分裂）。  
> **标记要全**：办公常用 Markdown 标记全集进 **组件库**；拖入/工具栏写入编辑面。  
> 工具栏与组件库 **同源同一套 id**。不做主题包 / 剪藏 / 多页签 / 公式 / 另存 Word。  
> （2026-09-16「取消设计面、只写源码」及 2026-09-29「仅编辑/预览」**由本条取代**。）

#### 0. 工具栏 vs 组件库 · 谁更快完成「完整格式化」？

| 维度 | 顶栏工具栏 | 右侧组件库（标签卡） |
|------|------------|----------------------|
| **发现「有哪些标记」** | 挤、难一眼看全 | **强**：卡片直接给「样子」（文字真渲染 / 图表迷你示意图） |
| **插入大块**（表/代码围栏/待办） | 弱 | **强**：点/拖进编辑窗即出骨架 |
| **打字中微调**（选中套加粗/行内代码） | **强**：少一步 | 弱（要移开视线点卡） |
| **学习成本** | 像 Word，但项一多就懵 | 稍复杂，但「这是什么标记」一目了然 |
| **完整格式化总耗时** | 项少时快；项全时找按钮更慢 | **完整场景更快**（少翻菜单、少背语法） |

**裁定（双轨同源，不二选一废一条）**

1. **组件库 = 主目录**：承载 **全部标记**；复杂但直观；拖入/点击 → 写入编辑面（辅助排版）。  
2. **工具栏 = 同源快键条**：同一套标记 id，方便选区秒套、少抬手；**禁止**工具栏另搞一套半残能力。  
3. **编辑 = 所见即所得**；**源码 = 同一 Markdown 的原文**；**预览 = 只读纸面**（含 mermaid 出图）。  
4. **一源 Markdown**：三面共用同一字符串。未改编辑面时切换不重排原文；编辑面改过之后，源码、预览和落盘都用这一次导出的结果。

#### A. 四层各管什么（禁止混称）

| 层 | 产品名 | 用户感知 | 存什么 | 不存什么 |
|----|--------|----------|--------|----------|
| **正文** | 一记事一文 | 「我在写这篇」 | 单一 `body`（Markdown） | 不做 TXT/MD 双格式；不做 HTML 真源 |
| **模式** | **编辑 / 源码 / 预览** | 三页签 | 仅 UI `view_mode` | 不另开设计面、不另存格式 |
| **组件库** | 右侧标记卡 | 卡片=拖入后的样子 | 写入编辑面 → MD | 不是范文包 |
| **工具栏** | 顶栏快键 | 与组件库同源 | 写入编辑面 → MD | 不得比组件库少一套「暗门」标记 |
| **模板** | 新建骨架 | 空白起点 | 空 Markdown | 禁止长范文 |

```
一记事一文（Markdown 落盘）
        │
        ├─ 编辑 ── 所见即所得；工具栏/组件库/手写/拖入 → 导出同一 MD
        ├─ 源码 ── 直接改这份 Markdown；语法高亮
        └─ 预览 ── 只读纸面；解释 MD 并展示（含图 / mermaid）
```

底栏 **效率指南**可展开、可收起，记住开关：语法速查、Ctrl+S / Ctrl+N、导入或拖入 `.md`。

#### B. 三面定义（硬）

| 面 | 产品称呼 | 定位 | 可否编辑 | 组件/工具栏 |
|----|----------|------|----------|-------------|
| **编辑** | 编辑 | **所见即所得**写作 | 可 | 显示；拖入落编辑面 |
| **源码** | 源码 | 直接改 Markdown | 可 | 隐藏；切回编辑后再用组件 |
| **预览** | 预览 | **只读**纸面阅读 | 否 | 隐藏 |

默认打开：**编辑**。从源码切回编辑或预览时，以源码正文重载所见即所得。

#### C. 标记全集（组件库必须覆盖 · 工具栏同源）

办公速记可用、且预览能解析的 Markdown 标记（要全，不留「只有工具栏有」）：

| 类 | 标记 |
|----|------|
| 标题 | H1～H6（`#` … `######`） |
| 强调 | 加粗 `**` · 斜体 `*` · 删除线 `~~` · 高亮 `==` |
| 列表 | 无序 `-` · 有序 `1.` · 待办 `- [ ]` |
| 块 | 引用 `>` · 代码围栏 ` ``` ` · 行内代码 `` ` `` · 分割线 `---` |
| 结构 | 表格 · 链接 · **图片（默认可调大小）** · **图标（默认小）** |
| 办公加分 | 时间戳 |
| **图表**（组件库「图表」分组集中） | ` ```mermaid `：流程图 TD/LR · 时序图 · 饼图 · 甘特图；拖入编辑窗；预览本机出图 |

文字标记：工具栏与组件库「常用」同源；卡片用预览同口径渲染「样子」。  
**图表标记集中在组件库**（不上工具栏挤占）；卡片画迷你示意图（流程/时序/饼/甘特），预览含 mermaid 时用本机 `resources/notepad/mermaid.min.js` 出图。

不做：公式、脚注、目录 TOC、主题包、剪藏、多页签。

#### D. 一致性硬规则

1. **一源**：落盘只有 Markdown；编辑面改动最终导出为此真源。  
2. **预览只解释**：手写或组件插入的内容，预览必须正确解析。  
3. **工具栏 id ≡ 组件库 id**：全量一致。  
4. **拖入只进编辑窗**：辅助排版；预览不接收拖入。  
5. **图片/图标 P0**：选/拖入编辑 → 带 `width` 的插图；默认中图 360 / 小图标 48，可改；预览过大图钳制。  

#### E. 主路径

1. 打开 → **编辑**所见即所得写作；选中一段就能加粗、改标题、套列表，再按一次取消。  
2. 行首打 `#`、`-`、`1.`、`>` 再按空格，直接变成标题、列表或引用；链接是可点文字，不是露出 `[]()`。  
3. 要改原文、或刚导入 AI 给的 `.md` → **源码**。查找替换 `Ctrl+F`，清除格式作用于当前段。  
4. 核对版式 → **预览**纸面。语法不清楚 → 底栏 **效率指南**。与剪贴板互拷、大纲、自动保存 —— 不变。

#### F. 明确不做

- 不做 TXT\|MD 双格式产品二分。  
- 不做 HTML/H5 第三格式真源、公式/脚注/主题包/剪藏/多页签。  
- 不做「工具栏一套、组件库另一套」文字标记；图表仅组件库集中提供。  
- 不在桌面暴露「导入记事本」传送门。

#### G. 验收口径

- [ ] **编辑 / 源码 / 预览**三面；编辑所见即所得；源码即 Markdown 原文；预览只读纸面。  
- [ ] 落盘为 Markdown；编辑↔源码↔预览不丢字。效率指南可收起。导入或拖入 `.md` 成一篇记事。  
- [ ] 组件库含上表标记全集；工具栏同源。  
- [ ] 拖组件进编辑窗即出对应版式。  
- [ ] 插图后编辑与预览可见。  

### 与相邻能力的边界（防凑数）

| 能力 | 关系 |
|------|------|
| `ocr_tool` | 截图翻译的底座之一；单独「图片转文字」仍保留，但不压过八件套 |
| `llm_assistant` / `integrations.translate` | 翻译引擎可走 LLM 或专用翻译 API；先评估再定 |
| `pomodoro` 番茄钟 | **未列入个人最高频** → **Hold·可隐藏**（专家组 2026-09-14 剔除排期） |
| `watermark_photo_generator` | **TOA 业务加水印**：目录规则 + 日期约束批量写回；≠ 已隐藏的日常 `image_watermark` |
| 大模型能力通例 | **小白默认本地完成**；有技术/电脑条件则引导探索增强（一件安装、≤2 步、步步引导）。无模型不砍入口、不逼装、不默认拖慢 |

---

## 0.6 专家组裁剪结论（2026-09-14 · 主理人口径）

> **口径**：已有功能要好用实用；将来需求须符合产品方向；没必要的任务剔除计划。  
> 席位：产品架构 + 工程管理（发版仍认 A10.4）。

### A · 必须做强 / 点验后收口（近程只干这些）

| 类 | 模块 | 动作 |
|----|------|------|
| Wave★ 做强 | `screenshot_tool` · `clipboard_history` · `quick_notepad` · `watermark_remover` · `ocr_tool` | 继续做强到可日用；点验清 gaps |
| Wave★ 收口 | `quadrant_tasks` · `screenshot_translate` · `directory_generator`(done) | **只点验**；禁止扩成项目管理 / 独立翻译页 |
| Wave F 收口 | `pdf_toolkit` · `file_packager` · `batch_rename` | **只点验**；禁止全能 PDF / 百规则重命名 |
| 培训壁垒 | `training_delivery_board` | 做强串链；**先于** generic_generator |
| 培训收口 | `assistant_recruit_post` · `assistant_outfit_swap` · `deliverable_directory_check` · `schedule_reminder` | 点验后收；不扩成招聘/影楼/大提醒系统 |
| 办公收口 | `llm_assistant` · `image_format_convert` · `image_to_scan` · `column_preview` · `email_client`(单账号 MVP) · `harness_agent` · `user_extensions` · `job_scheduler` · `notifications` | 主路径点验即停；邮箱**禁止**企微全量 |
| 探索收口 | `media_studio` · `open_pencil` · `drawio_web` | 现有能力点验；**不排**框选编辑/权重下载/bun 一键装/专属图标（无新压强） |

### B · 剔除计划 / 长期 Hold（Agent 停手 · 不占排期）

| 模块 / 事项 | 处置 |
|-------------|------|
| `pomodoro` | **Hold**；菜单可隐；不与四象限抢工期 |
| `image_adjust` | **Hold**；侧栏已隐；非压强不开 |
| `image_creator` | **Hold**（维持） |
| `comfyui_web` | **Hold**；文生图只走 `media_studio` |
| `engine_host_hub` | **Hold**；不当默认入口；禁半残六件套 |
| `generic_generator`（Excel 完整版） | **Hold** 至看板点验且主理人重开；近程剔除 Wave B 序号 |
| `generic_generator_simple` 增强（JSON 批量/样例库） | **不排增强**；维持现状 |
| `excel_cleaner` / Office 互转 / 查重清理 | **本波不做**（维持） |
| `email_client` 企微全量（多账号/话题/OAuth/Exchange） | **永久剔除对标**；只守单账号 MVP |
| 嵌个人微信窗（`wechat_host`） | **撤回**（2026-09-30）；见 §2 |
| `media_studio` 坐标框选 · 本机权重在线下载 | **从计划剔除**（无主理人新压强不开） |
| `notifications` 持久化历史 / 通道静音 | **不排**；试发点验即可 |
| `open_pencil` / `drawio_web` 依赖修复·导出联动·图标 | **不排**；仅点验现有内嵌 |

### C · 近程执行顺序

1. 主理人点验清：Wave★ + Wave F + 换装/招聘/看板 + 邮箱/翻译/OCR/记事本  
2. 代码只投：点验中发现的 **好用实用** 缺陷（崩/丢数据/主路径不通）  
3. 培训：看板串链做强优先于任何新通用生成  
4. 其余 Hold / 剔除项：**禁止**再开并行轨凑进度  

### D · 侧栏可见策略（2026-09-14 · 主理人「收掉未完成 / 推点验」）

- **开**：`done` 模块 + 近程点验池（Wave★ 侧栏项 · 培训串链/换装/招聘 · `email_client` · `quadrant_tasks` · **`column_preview` 桌面浏览**）  
- **开（引擎顶栏）**：`harness_agent` · `open_pencil` · `drawio_web`（及图片组 `media_studio`）；**勿**整组 `show:false` 导致顶栏「引擎」消失  
- **隐**：其余凑数 `mvp`（网页工作台、图转/扫描、通知、通用生成轻量、`llm_assistant`、`schedule_reminder` 等）及全部 Hold/stub  
- **商业发行暂隐（2026-10-12）**：Wave F（`pdf_toolkit` / `file_packager` / `batch_rename`）未点验前侧栏隐藏，点验后恢复  
- **仍隐（裁定）**：`engine_host_hub` · `comfyui_web` · `pomodoro` 等 Hold  
- **仍无侧栏**：`ocr_tool` / `screenshot_translate`（挂截图工具栏点验）  
- **主理人纠偏**：扩展/调度曾收口后按需恢复 `show:true`；桌面浏览保持点验池可见  

---

## 1. 平台底座（必须强）

| ID | 名称 | 场景 | 要做成什么样（最强标准） | 优先级 | 状态 | 开发前必评 |
|----|------|------|--------------------------|--------|------|------------|
| system_settings | 系统设置 | 主题、授权、菜单、热键、能力接入、诊断 | 分类清晰；菜单用户可配；LLM/OCR 可测连通；密钥不进仓；**进页要快**（页签懒加载、禁止打开时联网探测） | P0 | mvp→强 | 设置 IA、密钥存储；打开性能 |
| theme_preview | 控件库 | 研发/验收对照 | 控件×状态矩阵完整；业务页零旁路 | P0 | done | — |
| home | 首页 | 一键进高频工具 | 纯菜单驱动；**八件套置顶可配**；状态灯可信 | P0 | done | — |
| 菜单配置 | （设置内） | 客户自定义侧栏/首页 | 显示/排序/分组/恢复默认；保存即刷新壳 | P0 | done | — |

---

## 2. 白领日常增效（八件套之外）

| ID | 名称 | 应用场景 | 最强能力目标 | 优先级 | 状态 | 开发前技术评估方向 |
|----|------|----------|--------------|--------|------|-------------------|
| screenshot_tool | 截图工具 | 见 §0.5 | 见 §0.5 | **P0★** | mvp | ShareX / Snipaste / Flameshot |
| clipboard_history | 剪贴板历史 | 见 §0.5 | 见 §0.5 | **P0★** | mvp | Ditto / ClipX；Win32 监听 |
| quick_notepad | 快速记事 | 见 §0.5 | 见 §0.5 | **P0★** | mvp | 本地存储；与剪贴板联动 |
| quadrant_tasks | 任务管理 | 见 §0.5 | 见 §0.5 | **P0★** | mvp | 状态→日历→四象限；记事本传送 |
| watermark_remover | 去水印 | 见 §0.5 | 见 §0.5 | **P0★** | mvp | OpenCV inpaint vs LaMa vs IOPaint |
| image_watermark | 添加水印（日常） | 见 §0.5 · **已降级隐藏** | — | **P2** | mvp·隐藏 | 业务加水印用 `watermark_photo_generator` |
| directory_generator | 批量/快速建文件夹 | 见 §0.5 | 见 §0.5 | **P0★** | **done** | 2026-09-01 点验通过 |
| screenshot_translate | 截图翻译 | 见 §0.5 | 见 §0.5 | **P0★** | mvp | 挂工具栏；点验后收口 |
| ocr_tool | 图片转文字 | 截图识字、证件摘录 | 中英混排准；框选即出 | P0 | mvp | Tesseract vs PaddleOCR vs Windows OCR |
| harness_agent | 编码智能体 | 多轮 Agent、写码、改业务 | DeepSeek Harness Sidecar + 三栏指挥台 | P1 | done | docs/research/harness_agent-top3.md |
| llm_assistant | 大模型助手 | 润色、摘要 | OpenAI 兼容；流式；模板 | P1 | mvp | 流式 SSE；Ollama |
| image_format_convert | 图转文件 | 微信/邮件压缩 | 预设+批量 | P1 | mvp | Pillow / ImageMagick |
| image_to_scan | 转扫描件 | 合同扫描感 PDF | 透视/去阴影 | P1 | mvp | OpenCV 文档扫描 |
| image_adjust | 调整图片 | 旋转翻转明暗 | — | **Hold** | mvp·隐藏 | 专家组 2026-09-14：非压强不开 |
| batch_rename | 批量重命名 | 交付照片/课件编号 | 规则预览 + 可撤销；Wave F | **P1** | mvp | **点验后收口** |
| pomodoro | 番茄钟 | 专注计时 | — | **Hold** | mvp·可隐藏 | 专家组剔除排期；勿与四象限抢 |
| email_client | 邮箱代理 | 本机绑定收发带附件 | 单账号 IMAP+SMTP+附件 | **P2** | mvp·隐藏 | **仅** MVP 点验；企微全量已剔除 |

### 白领线建议不做或降级（避免凑数）

| ID | 原因 | 建议 |
|----|------|------|
| image_creator | 日常极少「从零造底图」 | **Hold**；菜单可隐藏 |
| photo_extractor | 偏培训班级批导出 | 归培训线 |
| watermark_photo_generator | 班级水印规则专用 | 归培训线 |
| pomodoro | 未进个人最高频 | **Hold**；可隐藏 |
| image_adjust | 非差异化 | **Hold** |
| email_client（对标企微全量） | 违背产品方向 | **永久剔除**；只守单账号 MVP |
| 个人微信窗口嵌进主区（`wechat_host`） | 主理人 2026-09-30：嵌窗没法用，功能已撤回 | **不做**。办公助手要支持在线沟通，走正规渠道，不嵌第三方客户端窗口 |

---

## 3. 培训运营业务（TOA 差异化 · 八件套做强后再排）

| ID | 名称 | 应用场景 | 最强能力目标 | 优先级 | 状态 | 开发前必评 |
|----|------|----------|--------------|--------|------|------------|
| deduction_note_formatter | 扣分备注整理 | Excel 复制→序号列表→回贴 | Ctrl+Shift+V 一键；历史；容错粘贴 | P0 | done | 保持行为；压测脏数据 |
| schedule_reminder | 班级日程提醒 | 开班节点提醒、导出场景表 | 五场景 xlsx；到期扫描；钉钉/邮件可选 | P1 | mvp | 钉钉/邮件可选联动 |
| schedule_format_converter | 排程格式转换 | 课表合并单元格→标准表 | 合并格解析正确率；多 Sheet | P1 | done | — |
| table_card_generator | 桌卡生成 | 学员姓名→台卡 PPT | Excel 映射；模板变量；合并/分文件 | P1 | done | — |
| teaching_assistant_resume | 助教简历 | 助教信息→简历 PPT | 完整版式；批量班级 | P1 | done | — |
| assistant_recruit_post | 助教招聘稿 | 班级名+地址→兼职助教招聘帖 | 命名即表单；话术锁定；复制即发 | P1 | mvp | docs/research/assistant_recruit_post-top3.md |
| assistant_outfit_swap | 助教打卡换装 | 打卡照目录全量换商务装 | 目录一键；着装预设；只换服装保水印 | P1 | mvp | docs/research/assistant_outfit_swap-top3.md |
| resume_extractor | 简历信息提取 | 简历文件→结构化字段 | 批处理；字段映射 | P2 | done | — |
| watermark_photo_generator | 生成水印照片 | 班级目录按规则加水印写回 | 子目录规则完整；默认写回 | P1 | done | 业务规则回归 |
| photo_extractor | 照片提取 | 目录→Word/PPT/PDF/长图 | 多格式稳定 | P1 | done | 大图分页 |
| directory_inspector | 目录透视 | 路径清单/空目录/命名/类型占比 | 相对路径列表；饼图占比；报告导出（≠TOA2 贴图检查） | P1 | done | — |
| deliverable_directory_check | 生成交付报告 | 班级交付目录质检 | Word 大纲+贴图；Excel 层级统计 | P1 | mvp | **仅点验**；不扩能力 |
| column_preview | MACOS风格桌面 | 苹果感目录浏览 | 分栏预览好用即收 | P1 | mvp | **点验后收口** |
| enhanced_directory_inspector | 交付材料生成 | 目录→交付 PPT | 双模板完整 | P1 | done | — |
| excel_row_to_column | 行转列 | 花名册转换 | 列选择；预览 | P2 | done | — |
| document_composer | 文档合成 | 多段材料合成 | 模板+页眉页脚 | P2 | done | — |
| generic_generator_simple | 通用生成（轻量） | 占位符填空 | 维持现状；**不排增强** | P2 | mvp | 专家组 2026-09-14 |
| generic_generator | 通用生成（Excel） | Excel 映射批量出文件 | — | **Hold** | stub | 看板点验且主理人重开前 **不排** |
| training_delivery_board | 培训交付看板 | 开班→交付串链 | 班级上下文不断；高级付费锚点 | **P0** | mvp | **做强优先**；先于 generic_generator |

---

## 4. 文件工具（Wave F · 必要四件套 · 要做就做强）

> 真相源：2026-09-01《文件/目录能力现状与必要规划》。对标格式大师 / 我的ABC / 优智文库等高频交集，**只做** PDF 三件套、交付向打包、批量重命名、目录生成收尾。  
> **不做本波**：`excel_cleaner`、Office 格式互转、Word 批量查找替换、查重/大文件清理、百工具凑数。

| ID | 名称 | 场景 | 最强目标 | 优先级 | 状态 | 必评 |
|----|------|------|----------|--------|------|------|
| directory_generator | 批量文件夹生成 | 粘贴名单建目录 | 见 §0.5 | **P0★** | **done** | 2026-09-01 点验通过 |
| pdf_toolkit | PDF 工具 | 材料/合同/课件 | **仅**合并 + 拆分 + 按页提取；禁止转 Word/OCR/水印 | **P1** | **mvp** | docs/research/pdf_toolkit-top3.md **approved**；待点验 |
| file_packager | 文件打包归档 | 交材料前目录→规范 zip | 预览清单；剔空夹；可选清单.txt | **P1** | **mvp** | docs/research/file_packager-top3.md **approved**；待点验 |
| batch_rename | 批量重命名 | 照片/课件/合同序号 | 预设 + 冲突门禁 + 撤销/链式提示 | **P1** | **mvp** | docs/research/batch_rename-top3.md **approved**；侧栏已开 |
| excel_cleaner | Excel 清洗 | 去空行重复 | 规则可存；预览 | P2 | stub | **本波不做**；有强痛再 Top3 |
| document_composer | 文档合成 | 多图合成 PDF/Word/PPT | 已 done，维持 | P2 | done | — |
| generic_generator_simple | 通用生成（轻量） | 占位符填空 | 维持 mvp | P2 | mvp | — |

---

## 5. 推荐开发序列（直接并行 · Wave★ 优先保障）

> **2026-09-14**：去掉开工障碍门禁；**有需求直接分轨写码**。对外版仍过 A10.4。  
> 下列顺序仅作优先级参考。

### Wave★ · 个人八件套（优先保障点验）

1. `screenshot_tool` — Snipaste 级体验（清晰度、多屏、历史、热键）  
2. `clipboard_history` — Ditto 级搜索与图片项  
3. `quick_notepad` — 热键秒开 + 与剪贴板互拷  
4. `quadrant_tasks` — **mvp**：点验拖拽/日历后清 gaps  
5. `watermark_remover` — 修复质量（含 LaMa 等评估结论）  
6. ~~`image_watermark`~~ — **已降级隐藏**（业务加水印用 `watermark_photo_generator`）  
7. `directory_generator` — 「粘贴名单 → 多文件夹」极速路径（**done** · 2026-09-01 点验）  
8. `screenshot_translate` — **mvp**：挂截图工具栏；待点验

### Wave F · 文件必要四件套（可与 Wave★ 分轨并行 · Top3 已 approved）

9. `pdf_toolkit` MVP — 合并 / 拆分 / 抽页（Top3 **approved**）  
10. `file_packager` — 交付向规范命名 zip（Top3 **approved**）  
11. `batch_rename` — 做强预设/冲突门禁/撤销与链式提示（Top3 **approved**；侧栏暂隐）  

### Wave B · 培训主链路 / 壁垒

12. **`training_delivery_board`** — 做强串链；点验 gaps  
13. `assistant_*` / `deliverable_directory_check` / `schedule_reminder` — **点验收口**  
14. `deduction_note_formatter` 回归（有缺陷才动）  
15. ~~`generic_generator`~~ — **Hold**（§0.6 B）；近程剔除  

### Wave C · 其它（默认不排）

16. `email_client` — **仅**单账号 MVP 点验；禁止企微全量  
17. OCR/图转/扫描 — 点验现有；`excel_cleaner` 仍本波不做  

### 明确 Hold / 本波不做（专家组 2026-09-14 扩写）

- `pomodoro` · `image_adjust` · `image_creator`  
- `comfyui_web` · `engine_host_hub`  
- `generic_generator`（至看板点验且主理人重开）  
- `excel_cleaner`、Office 互转、查重清理  
- `email_client` 企微全量；`media_studio` 框选/权重下载；通知持久化/静音；Pencil/Drawio 增强包  
- 详见 **§0.6**

---

## 6. 单功能开工检查表（精简 · 2026-09-14）

**有场景即可写码。** 下列为建议自检，**不是**停手条件（发版除外）。

- [ ] 场景一句话清楚
- [ ] 实现守分层 / widgets / 禁同步长联网 / `show_saved`
- [ ] 菜单 + manifest 已登记
- [ ] （可选）补 research 亮点文档
- [ ] 对外 Setup / 设当前版前过 **A10.4**
- [ ] 更新 OPS-01 一句


---

## 7. 与配置的关系

| 配置 | 作用 |
|------|------|
| `config/app.yml` → menu | 默认菜单 |
| `data/user/menu.yml` | 用户菜单覆盖（建议把八件套排前、番茄钟隐藏） |
| `config/migration_manifest.yml` | 迁移状态 / gaps |
| `config/integrations.yml` + secrets | OCR / LLM / 翻译 |
| 本文档 | **产品与开发优先级真相源** |

菜单隐藏 ≠ 删除能力；非八件套建议 `show: false`，降低首页噪音。

专家组裁剪真相源：**§0.6**。
