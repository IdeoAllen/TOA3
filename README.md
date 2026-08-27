# TOA3 — 赋能培训运营助手 3.0

**GitHub**：https://github.com/IdeoAllen/TOA3

PySide6 + Qt Designer + JSON 主题 → QSS 全局皮肤。

## 与 TOA2 关系

| 仓库 | 状态 |
|------|------|
| `../TOA` | **封板留存**（tkinter），仅维护 |
| `TOA3` | **主开发线**（本仓库） |

## 技术栈

- **UI**：PySide6、Qt Designer（`.ui` 布局 + Python 逻辑）
- **主题**：`config/themes/*.json` → `resources/qss/*.qss`
- **控件库**：`modules/gallery` + `widgets/`

## 快速开始

```powershell
cd TOA3
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts/sync_themes_from_toa2.py   # 可选：从 TOA2 同步主题 JSON
python scripts/sync_assets_from_toa2.py # 可选：从 TOA2 同步模板/示例
python scripts/gen_qss_from_theme.py
python -m app.main
```

## 目录

```
app/           应用入口、主题加载
assets/        随包模板 templates/、示例 samples/（只读）
config/themes/ 色板 JSON（与 DMS / TOA2 同源）
docs/standards/ 架构与开发规范
modules/       业务模块（逐步从 TOA2 迁移）
resources/qss/ 生成的 QSS（勿手改）
scripts/       主题同步、QSS 生成、验收
ui/            Qt Designer 文件（.ui）
widgets/       标准控件库（业务页只引用此处）
```

## 开发规范（摘要）

1. 业务页禁止 `setStyleSheet`、禁止硬编码颜色
2. 布局在 **Designer `.ui`** 或 **widgets 控件库**
3. 换主题只改 JSON / 重新生成 QSS
4. 新功能 **只在本仓库** 开发
5. **Agent 规则**：`.cursor/rules/toa3-*.mdc`（架构、授权、打包、Portal 裁定等）

**架构文档**（完整）：[`docs/architecture/README.md`](docs/architecture/README.md)

| 文档 | 内容 |
|------|------|
| [01-总览与原则](docs/architecture/01-总览与原则.md) | 目标、原则、技术选型 |
| [04-主题与QSS](docs/architecture/04-主题与QSS.md) | Design Tokens、换肤管线 |
| [05-控件库与Designer](docs/architecture/05-控件库与Designer.md) | 拖拽开发、widgets |
| [06-业务模块规范](docs/architecture/06-业务模块规范.md) | 新模块与 TOA2 迁移 |

规范速查：`docs/standards/UI架构.md`、`docs/standards/控件库规范.md`、**`docs/standards/Agent起手式.md`（新会话必读）**

## 版本

- **3.0.0-MVP** — 主壳 + 11 官方主题 + 控件库 + 系统设置

## MVP 验收

```powershell
python scripts/verify_mvp.py
```
