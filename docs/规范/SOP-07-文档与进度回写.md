# SOP-07 · 文档与进度回写

> **编号**：SOP-07 · **Skill**：`toa3-sop-docs-handoff`  
> **依据**：STD-01 · A0.6 · A0.7 · B7 · 文档宪法

## 1. 目的

会话结束与主理人反馈时，只更新规定文件；**意见必须进规范**，禁止平行规划或只留聊天。

## 2. 回写表

| 意图 | 只改 |
|------|------|
| 进度 / 交接 | `docs/handoff/OPS-01-交接与进度.md` |
| 协作说明 | `docs/handoff/OPS-02-协作任务说明.md`（+ json） |
| 工程标准/流程 | `docs/规范/STD-01-*.md` 或对应 `SOP-*.md` |
| 规范索引 | `docs/规范/00-规范清单.md` |
| 排期 | `docs/PROD-01-功能清单与优先级.md` |
| 产品叙事 | `docs/PROD-02-商务产品手册.md` |
| 愿景运行时 | `config/product.yml` |
| 架构裁定 | `docs/architecture/ARCH-*.md` |
| 模块灯色 | `config/migration_manifest.yml` |
| Top3 | `docs/research/<id>-top3.md` |

## 3. 主理人反馈 → 规范（强制）

| 反馈类型 | 落入 |
|----------|------|
| 编码/UI/性能/落盘/接口/完成灯 | STD-01 对应 **A** 条款（增改 ID） |
| 做事步骤/检查表 | 对应 **SOP-0x**（必要时同步 STD-01 **B**） |
| 产品边界/授权/引擎/壳 | 对应 **ARCH-xx** |
| 排期/优先级 / **并行分轨** | PROD-01（+ STD-01 A0.8/B9） |
| **统筹 / 商用交付 / 发版收口** | STD-01 A0.9 · A9.4 · A10.4–A10.5 · B9；打包 SOP-04；**商业验收 SOP-08** / `toa3-sop-commercial-release`；协作 OPS-02 |
| **专家组论证** | STD-01 **B10 / B10.1**（含 §3.5 写码过门）；结论写 OPS-01 + research/被论证条文 |
| 对外口径 | PROD-02 / `product.yml` |
| 仅进度事实 | OPS-01 一句即可 |

每次意见回写后：更新 OPS-01「本轮备忘」一行（改了哪个编号文件）。

## 4. 禁止

- 新建「方案N/总览2/指针页」  
- 把 `_archive/` 当现行或搬回现行目录  
- 往 `docs/` 写 Excel/Figma brief  
- 主理人改了规矩却只口头答应、不改 STD/SOP  
