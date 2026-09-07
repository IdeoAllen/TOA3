# UI 架构铁律（摘要）

完整说明见 [architecture/README.md](../architecture/README.md)。

## 五句话

1. **布局**在 Qt Designer（`ui/`）或已登记的 `widgets/`
2. **颜色字号**只在 `config/themes/*.json` → `resources/qss/*.qss`
3. **业务**禁止 `setStyleSheet`、禁止硬编码 hex
4. **控件库**（`modules/gallery`）= 唯一选用范围与验收清单
5. **新功能**只在本仓库开发，TOA2 已封板

## 主题切换

```powershell
python scripts/sync_themes_from_toa2.py   # 可选
python scripts/gen_qss_from_theme.py
# 重启应用，或系统设置中 apply_theme（规划）
```

## Designer

```powershell
pyside6-designer
```

Designer 内 **不预览** 全局 QSS；以运行控件库为准。

## 对照 TOA2

| TOA2 | TOA3 |
|------|------|
| `page_standard` / `Themed*` | `widgets/` |
| `apply_page_styles` | `apply_theme(app)` |
| `theme_preview` 页 | `modules/gallery` |
