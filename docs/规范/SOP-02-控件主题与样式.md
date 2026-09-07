# SOP-02 · 控件 · 主题 · 样式

> **编号**：SOP-02 · **Skill**：`toa3-sop-theme-control`  
> **依据**：STD-01 · A3 · B2 · B3

## 1. 目的

保证控件库唯一、主题 token 单一数据源、业务页零硬编码色。

## 2. 新增控件

1. 在 `widgets/` 实现  
2. 选择器写入主题/QSS 生成管线  
3. `modules/gallery` 展示全状态  
4. 加入 `CONTROL_CLASSES`  
5. 业务页方可引用  

例外：`# 控件库例外：…`

## 3. 改主题 / 改色

1. 只改 `config/themes/<id>.json` 的 `palette`（语义键见 STD-01 A3.3）  
2. `python scripts/gen_qss_from_theme.py`  
3. 提交 `resources/qss/`  
4. gallery + 主路径目测：主色、选中行、success/danger  

## 4. 禁止

业务 `setStyleSheet`、硬编码 hex、手改 QSS 文件、未入册控件直接上业务页。
