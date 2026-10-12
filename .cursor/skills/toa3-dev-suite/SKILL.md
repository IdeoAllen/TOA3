---
name: toa3-dev-suite
description: >-
  TOA3 桌面端开发规范全套入口（00清单+STD+SOP+Skill）。旧标准已下线。
  Use when starting any TOA3 desktop work, 规范, SOP, 开发规范清单, 新标准,
  or unsure which SOP/skill to load.
---

# TOA3 · 开发规范全套（入口）

**实现栈**：PySide6/Qt。**旧标准已归档下线**（`docs/_archive/OFFLINE.md`）— 禁止再引用。

## 必读

1. `docs/规范/00-规范清单.md`  
2. `docs/规范/STD-01-工程标准与流程.md`  

## 按任务选 SOP / Skill

| 任务 | SOP | Skill |
|------|-----|-------|
| 新功能/做强 | SOP-01 | `toa3-sop-new-feature` |
| 控件/主题 | SOP-02 | `toa3-sop-theme-control` |
| 登记/验收 | SOP-03 | `toa3-sop-module-accept` |
| 用例深化 | SOP-03 | `toa3-sop-quality-pipeline` |
| 打包发版 | SOP-04 | `toa3-sop-packaging` |
| 闪退排查 | SOP-05 | `toa3-sop-debug-crash` |
| 用户扩展 | SOP-06 | `toa3-sop-user-extension` |
| 文档/意见回写 | SOP-07 | `toa3-sop-docs-handoff` |
| 商业发行验收 | SOP-08 | `toa3-sop-commercial-release` |

主理人反馈规范类意见 → **必须**改 STD/SOP（SOP-07 / A0.7），再记 OPS-01。
