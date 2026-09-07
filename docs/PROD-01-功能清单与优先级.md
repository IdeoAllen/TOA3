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
| **个人高频优先** | 产品主理人日常八件套排在培训业务与其它白领增强之前做强 |
| **Top3 对标** | 每个功能开工前对标同类软件 Top3，取长补短；产出 `docs/research/<id>-top3.md` |
| **三独到处共创** | 每个功能必须与主理人一起论证出 **恰好 3 条**可感知、可测的独到之处，确认后再开发 |

### 优先级定义

| 级 | 含义 | 开做条件 |
|----|------|----------|
| **P0★** | 个人最高频（主理人每天用） | 立刻评估并做强；未达标前不扩其它功能 |
| **P0** | 白领/培训运营高频刚需，或平台底座 | 方案评估通过即可排期 |
| **P1** | 高频增强或培训主链路 | P0★ / 关键 P0 主路径稳定后 |
| **P2** | 低频 / 可替代 / 易凑数 | 默认不排期，除非有明确业务压强 |
| **Hold** | 暂不投入或合并进其他能力 | 清单保留，菜单可隐藏 |

### 状态

`done` 核心已对齐 · `mvp` 能用但未做强 · `stub` 仅占位 · `missing` 清单有、产品尚无 · `research` 评估中未写码

---

## 0.5 个人最高频八件套（开发真相源 · 优先于一切业务波次）

> 来源：产品主理人自述日常最高频。**先把这 8 个做到「个人愿意每天用」的强度，再扩培训与其它白领工具。**

| 序 | ID | 名称 | 应用场景 | 最强能力目标 | 现状 | 下一步 |
|----|-----|------|----------|--------------|------|--------|
| 1 | `screenshot_tool` | 截图 | 会议/反馈/发图；一切屏幕捕获入口 | 对标 Snipaste：多屏、S 重切、标注不糊、历史复用、热键稳、托盘唤起 | mvp | **Wave★-1** 评估后继续打磨 |
| 2 | `clipboard_history` | 剪贴板 | 反复粘贴文案/图；跨窗口搬运 | 对标 Ditto：文本+图、搜索、隐私、热键唤起、持久可靠 | mvp | **Wave★-2** |
| 3 | `quick_notepad` | 记事本 | 会中速记、临时草稿 | 热键秒开；列表搜索；与剪贴板一键互拷；本地不丢 | mvp | **Wave★-3** |
| 4 | `quadrant_tasks` | 四象限任务 | 重要×紧急任务看板；个人日计划 | 四象限拖拽；本地持久；热键唤起；逾期提醒；不过度项目管理化 | **mvp** | **Wave★-4** 点验后清 gaps |
| 5 | `watermark_remover` | 去水印 | 擦除豆包/角标/特殊照片水印 | **本地默认可完成**：轻量修复开箱即用；AI/LaMa **可选增强**（勾选才走），失败自动回退；框选+涂抹+自动角标 | mvp | **Wave★-5** |
| 6 | `image_watermark` | （日常通用加水印） | — | **侧栏默认隐藏**（主理人 2026-08-26）：TOA 加水印以业务 `watermark_photo_generator` 为准，勿与班级规则水印并列三入口 | mvp·隐藏 | 原 Wave★-6，已降级 |
| 7 | `directory_generator` | 快速创建多文件夹 | 一次建一批目录树（班级/项目/归档） | 粘贴名单即建；模板；预览；幂等；失败可续 | **done** | **Wave★-7** 已点验；Wave F 可开 |
| 8 | `screenshot_translate` | 截图翻译 | 框选屏幕 → 识字 → 译文（对照/替换） | 热键框选；原文+译文并列；可换引擎；可拷贝；延迟低 | **missing** | **Wave★-8**（可挂截图工具栏，勿单独凑菜单） |

### 与相邻能力的边界（防凑数）

| 能力 | 关系 |
|------|------|
| `ocr_tool` | 截图翻译的底座之一；单独「图片转文字」仍保留，但不压过八件套 |
| `llm_assistant` / `integrations.translate` | 翻译引擎可走 LLM 或专用翻译 API；先评估再定 |
| `pomodoro` 番茄钟 | **未列入个人最高频** → 降为 P2；菜单可隐藏；勿与四象限抢工期 |
| `watermark_photo_generator` | **TOA 业务加水印**：目录规则 + 日期约束批量写回；≠ 已隐藏的日常 `image_watermark` |
| 大模型能力通例 | **小白默认本地完成**；有技术/电脑条件则引导探索增强（一件安装、≤2 步、步步引导）。无模型不砍入口、不逼装、不默认拖慢 |

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
| quadrant_tasks | 四象限任务 | 见 §0.5 | 见 §0.5 | **P0★** | mvp | Eisenhower / Todoist 矩阵 / TickTick；本地 JSON/SQLite |
| watermark_remover | 去水印 | 见 §0.5 | 见 §0.5 | **P0★** | mvp | OpenCV inpaint vs LaMa vs IOPaint |
| image_watermark | 添加水印（日常） | 见 §0.5 · **已降级隐藏** | — | **P2** | mvp·隐藏 | 业务加水印用 `watermark_photo_generator` |
| directory_generator | 批量/快速建文件夹 | 见 §0.5 | 见 §0.5 | **P0★** | **done** | 2026-09-01 点验通过 |
| screenshot_translate | 截图翻译 | 见 §0.5 | 见 §0.5 | **P0★** | missing | Pot / Bob / Saladin；OCR+翻译链路；悬浮对照 UI |
| ocr_tool | 图片转文字 | 截图识字、证件摘录 | 中英混排准；框选即出 | P0 | mvp | Tesseract vs PaddleOCR vs Windows OCR |
| harness_agent | 编码智能体 | 多轮 Agent、写码、改业务 | DeepSeek Harness Sidecar + 三栏指挥台 | P1 | done | docs/research/harness_agent-top3.md |
| llm_assistant | 大模型助手 | 润色、摘要 | OpenAI 兼容；流式；模板 | P1 | mvp | 流式 SSE；Ollama |
| image_format_convert | 图转文件 | 微信/邮件压缩 | 预设+批量 | P1 | mvp | Pillow / ImageMagick |
| image_to_scan | 转扫描件 | 合同扫描感 PDF | 透视/去阴影 | P1 | mvp | OpenCV 文档扫描 |
| image_adjust | 调整图片 | 旋转翻转明暗 | 批量；预览 | P2 | mvp | Pillow EXIF |
| batch_rename | 批量重命名 | 交付照片/课件编号 | 规则预览 + 可撤销；Wave F | **P1** | mvp | docs/research/batch_rename-top3.md **approved** |
| pomodoro | 番茄钟 | 专注计时 | 托盘可见即可 | **P2** | mvp | 不与四象限抢优先级 |

### 白领线建议不做或降级（避免凑数）

| ID | 原因 | 建议 |
|----|------|------|
| image_creator | 日常极少「从零造底图」 | **Hold**；菜单可隐藏 |
| photo_extractor | 偏培训班级批导出 | 归培训线 |
| watermark_photo_generator | 班级水印规则专用 | 归培训线 |
| pomodoro | 未进个人最高频 | P2；可隐藏 |

---

## 3. 培训运营业务（TOA 差异化 · 八件套做强后再排）

| ID | 名称 | 应用场景 | 最强能力目标 | 优先级 | 状态 | 开发前必评 |
|----|------|----------|--------------|--------|------|------------|
| deduction_note_formatter | 扣分备注整理 | Excel 复制→序号列表→回贴 | Ctrl+Shift+V 一键；历史；容错粘贴 | P0 | done | 保持行为；压测脏数据 |
| schedule_reminder | 班级日程提醒 | 开班节点提醒、导出场景表 | 五场景 xlsx；到期扫描；钉钉/邮件可选 | P1 | mvp | 钉钉/邮件可选联动 |
| schedule_format_converter | 排程格式转换 | 课表合并单元格→标准表 | 合并格解析正确率；多 Sheet | P1 | done | — |
| table_card_generator | 桌卡生成 | 学员姓名→台卡 PPT | Excel 映射；模板变量；合并/分文件 | P1 | done | — |
| teaching_assistant_resume | 助教简历 | 助教信息→简历 PPT | 完整版式；批量班级 | P1 | done | — |
| resume_extractor | 简历信息提取 | 简历文件→结构化字段 | 批处理；字段映射 | P2 | done | — |
| watermark_photo_generator | 生成水印照片 | 班级目录按规则加水印写回 | 子目录规则完整；默认写回 | P1 | done | 业务规则回归 |
| photo_extractor | 照片提取 | 目录→Word/PPT/PDF/长图 | 多格式稳定 | P1 | done | 大图分页 |
| directory_inspector | 目录透视 | 路径清单/空目录/命名/类型占比 | 相对路径列表；饼图占比；报告导出（≠TOA2 贴图检查） | P1 | done | — |
| deliverable_directory_check | 生成交付报告 | 班级交付目录质检 | Word 大纲+贴图；Excel 层级图片统计（TOA2 DirectoryChecker） | P1 | mvp | Top3 待确认；主理人点验 |
| column_preview | MACOS风格桌面 | 苹果感目录浏览 | 分栏/图标/列表；彩色标签；侧栏折叠；新建 | P1 | mvp | docs/research/column_preview-top3.md |
| enhanced_directory_inspector | 交付材料生成 | 目录→交付 PPT | 双模板完整 | P1 | done | — |
| excel_row_to_column | 行转列 | 花名册转换 | 列选择；预览 | P2 | done | — |
| document_composer | 文档合成 | 多段材料合成 | 模板+页眉页脚 | P2 | done | — |
| generic_generator_simple | 通用生成（轻量） | 占位符填空 | 与完整版边界清晰 | P2 | mvp | — |
| generic_generator | 通用生成（Excel） | Excel 映射批量出文件 | 任务 GUI；映射驱动 | P1 | stub | **必须先评估**；禁止轻量凑数 |

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

## 5. 推荐开发序列（严格按个人高频）

每步：**全网检索 → 方案一页纸 → 实现 → 对照验收**。未过评估不准开工。

### Wave★ · 个人八件套（当前主线）

1. `screenshot_tool` — Snipaste 级体验（清晰度、多屏、历史、热键）  
2. `clipboard_history` — Ditto 级搜索与图片项  
3. `quick_notepad` — 热键秒开 + 与剪贴板互拷  
4. `quadrant_tasks` — **mvp**：点验拖拽/日历后清 gaps  
5. `watermark_remover` — 修复质量（含 LaMa 等评估结论）  
6. ~~`image_watermark`~~ — **已降级隐藏**（业务加水印用 `watermark_photo_generator`）  
7. `directory_generator` — 「粘贴名单 → 多文件夹」极速路径（**done** · 2026-09-01 点验）  
8. `screenshot_translate` — **missing**：框选→OCR→翻译（优先挂截图工具栏/热键，勿空菜单）

### Wave F · 文件必要四件套（前置已满足 · 可写码 · 先于 Wave B）

9. `pdf_toolkit` MVP — 合并 / 拆分 / 抽页（Top3 **approved**）  
10. `file_packager` — 交付向规范命名 zip（Top3 **approved**）  
11. `batch_rename` — 做强预设/冲突门禁/撤销与链式提示（Top3 **approved**；侧栏暂隐）  

### Wave B · 培训主链路（八件套达标后再开）

12. `schedule_*` / `table_card` / `teaching_assistant_resume`  
13. `generic_generator`（Excel 完整版 · **必须先评估**）  
14. `deduction_note_formatter` 回归加固  

### Wave C · 其它

15. OCR 引擎增强、图转/扫描、`excel_cleaner`（有强痛再开）  

### 明确 Hold / 本波不做

- `image_creator`、为菜单堆 stub、用番茄钟替代四象限  
- `excel_cleaner`、Office 互转、查重清理（让位系统/Everything）  

---

## 6. 单功能开工检查表（强制 · Top3 门禁）

**未完成 Top3 + 与主理人共创并确认 3 条独到之处 → 禁止写该功能业务代码。**

- [ ] 写清 **用户场景**（谁、何时、输入输出）
- [ ] **同类软件 Top3 分析**（取长补短）：`docs/research/<module_id>-top3.md`
- [ ] **与主理人一起论证**，产出 **恰好 3 条独到之处**（主张 + 可感知价值 + 可测验收），勾选文档 §3.5「主理人已确认」
- [ ] 选定技术方案及否决项（写入同一文档 §4，并说明如何兑现三条）
- [ ] 定义可测的 **「最强」验收标准**（含三条独到处）
- [ ] 确认：架构规范 · 性能 · 高品质；菜单可维护、控件库、integrations
- [ ] 文档状态改为 `approved` 后再动手
- [ ] 更新 `config/migration_manifest.yml`


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
