# TOA3 · Agent 交接总册

> **文档宪法（先读）：** [`../README.md`](../README.md)  
> **唯一进度：** [`AGENT_RELAY.md`](./AGENT_RELAY.md)  
> 更新：2026-09-07 · 本文件只保留 Agent 开场要点；细则见宪法与规则，**禁止**在此复制第二套规划。

---

## 开场 30 秒

| 问 | 答 |
|----|----|
| 产品 | 办公极简伴侣（运营宝 / TOA3），PySide6 |
| 只改哪 | **只改 TOA3**；TOA2 封板 |
| 写码门禁 | Top3 + 3 独到处经主理人确认 |
| 完成 | `gaps` 空且主理人认可才 `done` |
| 进度写哪 | **只写** `AGENT_RELAY.md` |

愿景文案：`config/product.yml` · 叙事：`docs/商务产品手册.md` · 排期：`docs/功能清单与优先级.md`

---

## 必遵规则（alwaysApply）

目录：`.cursor/rules/toa3-*.mdc`（含 `toa3-docs-canon`）

高频：`toa3-product-core` · `toa3-feature-top3-research` · `toa3-feature-acceptance` · `toa3-office-suite-shell` · `toa3-docs-canon`

## Skill

| Skill | 何时 |
|-------|------|
| `toa3-add-feature` | 新功能 / 做强 |
| `toa3-quality-test-pipeline` | 用例 / 质量 |
| `toa3-debug-crash` | 闪退 / WebEngine |
| `toa3-user-extension` | 用户扩展 |

## 工程标准合订

[`../工程标准.md`](../工程标准.md)（现行唯一；旧 standards 在 `_archive/standards/`）

## 架构现行

[`../architecture/README.md`](../architecture/README.md)

## 四象限种子

`collab_tasks.json` → `python scripts/seed_collab_tasks.py --edition both --wipe-collab`  
看板说明见 `AGENT_RELAY.md`（不再维护第二份任务长文）。

## 验收

`python scripts/verify_all.py` · `audit_migration.py` · 主理人点验回写 gaps
