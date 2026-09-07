# TOA3 文档目录

> 更新：2026-09-07  
> **桌面端开发规范全套已全面上线**（对标 WinForm 规范清单 + SOP + Skill；实现栈 PySide6/Qt）  
> **旧标准/流程已下线**：[`_archive/OFFLINE.md`](./_archive/OFFLINE.md) — 禁止再当门禁

## 入口（先读）

| 编号 | 文件 | 职责 |
|------|------|------|
| **00** | [`规范/00-规范清单.md`](./规范/00-规范清单.md) | **总清单**（唯一索引） |
| **STD-01** | [`规范/STD-01-工程标准与流程.md`](./规范/STD-01-工程标准与流程.md) | 唯一工程标准（A）+ 流程纲要（B） |
| **SOP-01…07** | [`规范/SOP-*.md`](./规范/) | 作业指导书 |

Agent 总入口 Skill：`toa3-dev-suite`  
主理人意见 → 必须回写 STD/SOP（SOP-07），禁止只留在聊天。

## 产品 · 运维

| 编号 | 文件 |
|------|------|
| PROD-01 | [`PROD-01-功能清单与优先级.md`](./PROD-01-功能清单与优先级.md) |
| PROD-02 | [`PROD-02-商务产品手册.md`](./PROD-02-商务产品手册.md) |
| OPS-01 | [`handoff/OPS-01-交接与进度.md`](./handoff/OPS-01-交接与进度.md) |
| OPS-02 | [`handoff/OPS-02-协作任务说明.md`](./handoff/OPS-02-协作任务说明.md) |

## 架构裁定

[`architecture/`](./architecture/) → `ARCH-01` … `ARCH-09`（见规范清单 §4）

## Top3 附件

[`research/`](./research/) → `<module_id>-top3.md`

## 配置真相源

| 路径 | 用途 |
|------|------|
| `config/themes/*.json` | 颜色 token |
| `config/integrations.yml` | 出站能力 |
| `config/feature_packs.yml` | SKU |
| `config/migration_manifest.yml` | 灯色 + gaps |
| `config/app.yml` | 菜单 / 热键 / license URL |
| `config/product.yml` | 愿景文案 |
| `app/version.py` | `APP_VERSION` |
| `scripts/verify_all.py` | 测试门禁 |

## 禁止

- 新建平行「规范2 / 流程总览」  
- `_archive/` 当现行门禁  
- 往 `docs/` 写 Excel / Figma brief  

归档：[`_archive/`](./_archive/)
