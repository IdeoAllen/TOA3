---
name: toa3-sop-theme-control
description: >-
  TOA3 SOP-02 控件/主题/样式：CONTROL_CLASSES、gallery、gen_qss。
  Use when 新控件、改主题、改色、换肤、setStyleSheet、gallery.
---

# SOP-02 · 控件 · 主题 · 样式（Skill）

**正文**：`docs/规范/SOP-02-控件主题与样式.md`  
**标准**：STD-01 · A3 · B2 · B3

- 新控件：widgets → QSS 管线 → gallery → `CONTROL_CLASSES`  
- 改色：只改 `config/themes/*.json` → `python scripts/gen_qss_from_theme.py`  
- 禁止业务 `setStyleSheet` / 硬编码 hex / 手改 QSS
