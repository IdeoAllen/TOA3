---
name: toa3-sop-quality-pipeline
description: >-
  TOA3 高质量用例流水线：需求/改动→测试地图→用例生成→隐藏场景补全→质量评审，
  并挂 Agent 自测脚本。Use when 写验收用例、测试设计、补场景、用例评审、
  质量门禁、自测、清 gaps、联调清单、PRD 拆测试点、覆盖率、回归设计、
  功能交付前验收、主理人点验清单。
---

# TOA3 · 高质量用例流水线（四环组合拳）

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

参考业界「需求拆解 → 用例生成 → 场景补全 → 质量评审」Skill 流水线，
**落到 TOA3 壳层 / 模块 / Agent 自测**，禁止只产出 Excel 空想用例。

> 原则：**AI 出初稿，Agent 自跑脚本为真，主理人点验才能清 gaps / 标 done。**

## 何时启用

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

- 功能交付、改 bug、清 `migration_manifest` gaps 前  
- 用户说：写用例 / 验收清单 / 补场景 / 质量评审 / 自测  
- Wave★ 模块做强、壳层/WebEngine 回归  

## 铁律

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

1. **不臆造需求** — 地图只从 PRD / research / gaps / 代码行为提取；不明则标「需确认」。  
2. **每个 Skill 环可人工确认点** — 勿一口气「全自动定稿」。  
3. **用例必须可执行** — 优先映射到 `scripts/verify_*.py` / `debug_*.py` / `stress_*.py`；无脚本则补脚本或写清手动步骤。  
4. **遵守产品门禁** — Top3+三独到处、`show_saved`、禁止进页同步联网、菜单只来自 yaml。  
5. **渐进式披露** — 本文件只放流程；模板见 `references/`。

---

## 流水线（必须按序）

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

```text
需求 / gaps / research / 改动 diff
        ↓
① 测试地图（prd-to-test-map）
        ↓  [可选：主理人/Agent 确认功能清单]
② 用例初稿（test-case-generator）
        ↓
③ 隐藏场景补全（test-scenario-completion）
        ↓
④ 质量评审（test-case-reviewer）
        ↓
⑤ TOA3 落地：脚本断言 + 跑绿 + 回写 gaps/文档
```

详细模板：[`references/four-skills.md`](references/four-skills.md)  
TOA3 脚本映射：[`references/toa3-script-map.md`](references/toa3-script-map.md)

---

## ① 测试地图（必须先做）

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

输出四块（缺信息写「需确认」）：

| 块 | 内容 |
|----|------|
| 功能清单 | F1… 一句话 |
| 业务规则 | R1… 状态/权限/限制 |
| 数据约束 | D1… 类型/范围/必填 |
| 风险预判 | 高/中/低（并发、边界、WebEngine、HiDPI、切页） |

TOA3 额外必问：

- 入口：顶栏子模块 → 侧栏 → 热键/托盘/覆盖层？  
- 完成反馈：是否须 `show_saved`？  
- 是否 WebEngine / 共享 View / 离引擎 shutdown？  

## ② 用例生成

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

表格字段：编号 · 场景 · 前置 · 步骤 · 预期 · 类型（正常/异常/边界/权限）· 优先级(P0/P1/P2) · **自动化**（脚本名或「手测」）

规则：每功能 ≥1 正向 + ≥3 异常/边界；步骤可执行。

## ③ 场景补全（防漏）

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

强制扫：

1. 并发 / 狂切菜单 / 引擎↔业务  
2. 状态流转（未启动/启动中/已嵌入/已销毁）  
3. 数据一致性（配置 yaml、module_data、license）  
4. 边界组合（HiDPI 125/150、无网、正式版+开发版双开）  
5. 历史故障（见 `toa3-sop-debug-crash`：遮罩挡点击、beforeunload 串引擎、DataTable AV）  

## ④ 质量评审

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

四维打分（百分制）+ 待改进项 + 结论（通过 / 有条件通过 / 不通过）：

1. 覆盖完整性（含四类场景）  
2. 规范性（前置-步骤-预期齐全）  
3. 逻辑一致性  
4. 优先级合理性  

**TOA3 加分项：** 是否有 Agent 可跑脚本；是否触碰超边（Portal 菜单下发等）。

## ⑤ 落地与自测（交付门禁）

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

| 级别 | 动作 |
|------|------|
| 壳/引擎 | `verify_shell_hardening.py` → `debug_engines_to_business.py` → `stress_engines_business.py` |
| 总门禁 | `python scripts/verify_all.py` |
| 模块 | 有则跑模块脚本；无则补最小断言或 stress 路径 |
| 回写 | gaps 只清**已兑现且自测过**项；「主理人点验」类**不得**代清 |

原生闪退查：`common/logs/toa3_faulthandler.log`。

---

## 与其它 Skill 分工

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

| Skill | 分工 |
|-------|------|
| `toa3-sop-new-feature` | 开工前 Top3 + 三独到处 |
| `toa3-sop-debug-crash` | 闪退/闪烁/点不动排错 |
| **本 Skill** | 验收用例质量与自测闭环 |

---

## 输出给用户的最短汇报

> 对应 SOP：见 `docs/规范/` 目录；规范清单 `docs/规范/00-规范清单.md`。

```text
地图：F?/R?/风险?
用例：P0 n 条 · 已挂脚本 …
补全：隐藏场景 …
评审：xx/100 · 结论
自测：脚本名 EXIT=0
gaps：清了哪些 / 留给主理人点验哪些
```
