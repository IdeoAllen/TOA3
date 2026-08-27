# 04 · 主题与 QSS

## 1. 设计令牌四层（对标 Design Tokens）

```
L1 原语 Primitive     palette.primary = "#2563EB"
L2 语义 Semantic      row_selected, success_bg, progress_fill …
L3 组件 Component    QSS 选择器：QPushButton[class="primary"]
L4 业务 Business     禁止写色；只用 widgets + 全局 QSS
```

参考：[W3C Design Tokens](https://www.w3.org/community/design-tokens/)、[Martin Fowler — Token-Based UI](https://martinfowler.com/articles/design-token-based-ui-architecture.html)

**向下引用**：QSS 里写语义色值（由 JSON 展开），业务不写 hex。

## 2. 文件与管线

```
config/themes/dms_blue.json
        │
        │  scripts/sync_themes_from_toa2.py（可选，从 TOA2 拉取）
        │
        ▼
scripts/gen_qss_from_theme.py
        │
        ▼
resources/qss/dms_blue.qss          ← 勿手改
        │
        ▼
app/theme_loader.apply_theme(app, "dms_blue")
        │
        ▼
QApplication.setStyleSheet(qss)     ← 全局一次
```

### 2.1 启动时（`app/main.py`）

```python
from app.theme_loader import DEFAULT_THEME, apply_theme

apply_theme(app, DEFAULT_THEME)  # 默认 dms_blue
```

### 2.2 换主题（规划：系统设置）

1. 用户选择 `dms_green` 等
2. 写入 `config/app.yml` 的 `theme` 字段
3. `apply_theme(app, new_id)` 立即生效
4. 各模块 `on_theme_changed()` 仅处理非 QSS 资源（图标等）

## 3. JSON 结构（与 TOA2 兼容）

TOA3 **当前消费** `palette` + `metrics` + `fonts`（QSS 生成器逐步扩展）。

| 字段 | 用途 |
|------|------|
| `palette` | 全部颜色令牌 |
| `fonts` | 字号阶梯（映射到 QSS `font-size`） |
| `metrics` | padding、行高（映射到 QSS `min-height` 等） |
| `controls` | TOA2 ttk 用；TOA3 可逐步改为 QSS 片段模板 |

TOA2 的 `controls.Page.*` **不** 在 Qt 运行时读取；仅作迁移期对照。

## 4. 语义色清单（必须在 QSS 覆盖）

| 令牌 | 典型用途 |
|------|----------|
| `primary` / `primary_hover` / `primary_pressed` | 主按钮、聚焦环 |
| `background` / `surface` | 页面底、卡片面 |
| `text_primary` / `text_secondary` / `text_disabled` | 正文、辅助、禁用 |
| `border_default` / `border_focus` | 输入框边框 |
| `row_selected` / `row_selected_text` | 表格选中（非系统蓝） |
| `progress_fill` / `progress_bg` | 进度条 |
| `success_bg` / `warning_bg` / `danger_bg` / `info_bg` | 语义条 |
| `header_bg` / `header_fg` | 表头、Shell 侧栏 |
| `surface_sidebar` / `nav_*` | 导航 |

完整键集见 `config/themes/dms_blue.json`。

## 5. QSS 与控件 class 约定

业务通过 **Qt 属性 `class`**（或 `objectName`）区分样式，**不是** C++ 类名。

| class / 选择器 | 控件 |
|----------------|------|
| `QLabel[class="page-title"]` | 页标题 14pt |
| `QLabel[class="section-title"]` | 分区 12pt |
| `QLabel[class="hint"]` | 辅助 9pt |
| `QLabel[class="semantic-success"]` 等 | 语义条 |
| `QPushButton[class="primary"]` | 主按钮 |
| `QPushButton[class="danger"]` | 危险按钮 |
| `QPushButton#NavButton:checked` | 导航选中 |

设置方式：

```python
btn.setProperty("class", "primary")
btn.style().unpolish(btn)
btn.style().polish(btn)
```

（`widgets` 封装内完成，业务不手写。）

## 6. 字号阶梯（与 TOA2 一致）

| 角色 | pt | 令牌 |
|------|-----|------|
| 页标题 | 14 bold | `FONT_PAGE_TITLE` |
| 分区标题 | 12 bold | `FONT_SECTION` |
| 正文/按钮 | 10 | `FONT_BODY` |
| 辅助 | 9 | `FONT_SMALL` |

定义：`widgets/metrics.py`；QSS 全局默认 10pt + class 覆盖。

## 7. 尺寸令牌

| 令牌 | 值 | 用途 |
|------|-----|------|
| `BUTTON_MIN_HEIGHT` | 32 | 按钮、可点区域 |
| `INPUT_PADDING_V` | 8 | 输入框内边距 |
| `TREE_ROW_HEIGHT` | 32 | 表格行高 |
| `CONTROL_GAP` | 8 | 控件间距 |

## 8. 开发命令

```powershell
# 从 TOA2 同步全部主题 JSON
python scripts/sync_themes_from_toa2.py

# 生成 QSS
python scripts/gen_qss_from_theme.py

# 验证（规划）
python scripts/verify_gallery.py
```

## 9. 已知限制

- Qt Designer **无法预览**全局 QSS → 以 **控件库运行页** 为验收标准
- `QComboBox` 下拉列表部分样式受平台影响，可能略偏原生
- 自定义绘制控件（Canvas 绘图）需单独读 `palette`，标注「控件库例外」

## 10. 下一章

[05-控件库与Designer](05-控件库与Designer.md)
