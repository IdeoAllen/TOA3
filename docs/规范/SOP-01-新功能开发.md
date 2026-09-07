# SOP-01 · 新功能 / 做强

> **编号**：SOP-01 · **Skill**：`toa3-sop-new-feature`  
> **依据**：STD-01 · B1 · A*  
> **排期**：PROD-01 · **进度**：OPS-01 · **超边**：ARCH-03

## 1. 目的

在 TOA3 桌面端新增或做强功能时，保证 Top3 门禁、三独到处、登记与验收完整可复现。

## 2. 适用范围

新模块、大增强、从 TOA2 移植业务逻辑（UI 必须用 Qt/widgets 重做）。

## 3. 输入 / 输出

| 输入 | 输出 |
|------|------|
| 主理人场景描述 | `docs/research/<id>-top3.md`（`approved`） |
| — | `modules/<id>/` + 菜单 + manifest |
| — | OPS-01 一句进度；gaps 更新 |

## 4. 步骤（不可跳）

| 步 | 动作 | 完成判据 |
|----|------|----------|
| 1 | 定场景：谁/何时/输入/输出/失败提示 | 主理人确认 |
| 2 | Top3 对标；草案恰好 3 条独到处 | 写入 research 文档 |
| 3 | 与主理人逐条论证独到处 | 勾选确认；状态 `approved` |
| 4 | 技术方案（栈/否决/落点/性能/验收） | 同 research 文档可测 |
| 5 | 实现：兑现独到处；遵守 STD-01 A | 可运行 |
| 6 | 执行 SOP-03 登记 | `audit_migration` 通过 |
| 7 | 执行 SOP-03 验收 + 建议 `toa3-sop-quality-pipeline` | 点验/gaps |
| 8 | SOP-07 回写 OPS-01 | 进度已更新 |

## 5. 停手条件

无 Top3 文档 / 未确认 3 独到处 / 非 `approved` → **禁止写业务码**。

## 6. 模板与命令

- 模板：`docs/research/_TEMPLATE-top3.md`
- `python scripts/verify_all.py` · `python -m app.main`
