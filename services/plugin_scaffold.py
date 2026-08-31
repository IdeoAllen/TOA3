# -*- coding: utf-8 -*-
"""生成 TOA 业务插件脚手架（契约 + AGENTS + 空 BasePage）。"""
from __future__ import annotations

import re
from pathlib import Path

from services.menu_registry import GROUP_ORDER, MIGRATED_MODULES
from services.plugin_pack import parse_plugin_root

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


def suggest_plugin_id(name: str) -> str:
    """从显示名生成 id；中文等非 ASCII 名用安全编号，不要求用户懂英文。"""
    import time

    raw = re.sub(r"[^a-zA-Z0-9]+", "_", (name or "").strip()).strip("_").lower()
    if raw and re.match(r"^[a-z]", raw) and len(raw) >= 2:
        return raw[:48]
    return f"ext_{int(time.time()) % 1_000_000}"


def _pascal(plugin_id: str) -> str:
    return "".join(p.capitalize() for p in plugin_id.split("_") if p) + "Page"


def write_requirements_md(
    root: Path | str,
    *,
    name: str,
    description: str,
) -> Path:
    """把用户需求落盘，供智能体只读本目录即可开工。"""
    path = Path(root).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    display = str(name or path.name).strip() or path.name
    body = str(description or "").strip()
    text = (
        f"# 需求说明 · {display}\n\n"
        "（用户在「系统 → 扩展」填写；智能体实现时以本文为准。）\n\n"
        f"{body}\n"
    )
    out = path / "REQUIREMENTS.md"
    out.write_text(text, encoding="utf-8")
    return out


def read_requirements_md(root: Path | str) -> str:
    p = Path(root).expanduser().resolve() / "REQUIREMENTS.md"
    if not p.is_file():
        return ""
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError:
        return ""
    lines: list[str] = []
    for line in raw.splitlines():
        if line.startswith("# ") and not lines:
            continue
        if line.startswith("（用户在") and not lines:
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def host_api_markdown(*, plugin_id: str, surface: str = "qt") -> str:
    """写进扩展目录的宿主 API 速查，避免智能体去 Read 宿主源码。"""
    web_section = ""
    if str(surface or "qt").strip().lower() == "webview":
        web_section = """

## WebView 桥 API（surface=webview · JS 侧）

页面须引入：

```html
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="toa_bridge.js"></script>
```

```javascript
TOA.ready(function (toa) {
  toa.reportStatus('就绪', 'success');
  toa.showSaved('已保存', toa.outputDir());
  var pal = TOA.parsePalette(toa.themePalette());
});
```

| 方法 | 说明 |
|------|------|
| `toa.pluginId()` | 扩展 id |
| `toa.pluginName()` | 显示名 |
| `toa.dataDir()` | 数据目录绝对路径 |
| `toa.outputDir()` | 输出目录绝对路径 |
| `toa.reportStatus(text, level)` | level: info/success/warning/error |
| `toa.showSaved(text, path)` | 绿色完成 + 打开所在目录 |
| `toa.readTextFile(relative)` | 读 data 目录内相对路径 |
| `toa.writeTextFile(relative, content)` | 写 data 目录内相对路径 |
| `toa.themePalette()` | 主题 JSON 字符串 |
| `toa.themeId()` | 当前主题 id |

资源只放 `ui/`；导航默认限制在扩展目录内；联网须 `allow_network = true`。
"""
    qt_entry = (
        f"宿主 WebEngine 加载：`ui/index.html`（见 plugin.toml entry.web_root）。\n"
        if str(surface or "qt").strip().lower() == "webview"
        else f"唯一入口：`modules/{plugin_id}/{plugin_id}_page.py`"
    )
    return f"""# 宿主 API 速查（只读本文件，禁止去扫 TOA 源码）

本文件已复制进扩展沙箱。需要 API 时 **只读这里**，不要 Read/Grep  
`TOA3/widgets`、`TOA3/core`、`TOA3/services`。

## 常用 import（surface=qt）

```python
from core.base_page import BasePage
from core.status_service import StatusLevel
from core.user_messages import show_saved, show_info, show_warning, show_error, ask_confirm
from services.storage_paths import module_data_dir, module_output_dir
from services.os_open import open_in_file_manager
from widgets import (
    ScrollPage, PageHeader, FormSection, HintLabel, SemanticLabel,
    LineEdit, PlainTextEdit, ReadOnlyPlainTextEdit, DateEdit, ComboBox,
    CheckBox, Switch, PrimaryButton, SecondaryButton, DataTable,
)
```

## 控件清单（`from widgets import …`）

PageTitle, SectionTitle, HintLabel, SemanticLabel,  
PrimaryButton, SecondaryButton, DangerButton, MessageKindButton, InlineButton,  
LineEdit, PasswordLineEdit, PlainTextEdit, ReadOnlyPlainTextEdit, TextEdit, ReadOnlyTextEdit,  
ComboBox, SpinBox, DateEdit, CalendarWidget, CheckBox, Switch, RadioButton, Slider,  
FormSection, ScrollPage, PageHeader, HBox, VBox, FormRow, PathRow, GridBox, SplitPane,  
ListWidget, TreeWidget, ProgressBar, TabWidget, DataTable, DialogButtonRow,  
ListPanel, ManageTablePanel, FormEditDialog,  
ToolLaunchCard, StatusDot, ThemePicker

## 关键函数签名（照抄即可）

```python
show_saved(self, "已保存", path)
data_dir = module_data_dir("{plugin_id}", create=True)
out_dir = module_output_dir("{plugin_id}", create=True)
self.report_status("说明文字", level=StatusLevel.SUCCESS)
```

## 入口

{qt_entry}  
禁止 `from modules.{plugin_id}...`（那是官方 modules 命名空间）。
{web_section}
"""


def agents_markdown(*, plugin_id: str, name: str, plugin_root: str = "", surface: str = "qt") -> str:
    from services.plugin_sandbox import isolation_rules_text, user_extensions_root

    root_hint = plugin_root or str(user_extensions_root() / plugin_id)
    surface = str(surface or "qt").strip().lower()
    web_block = ""
    if surface == "webview":
        web_block = """
## Web 面（本扩展 surface=webview）

1. **只改** `ui/` 目录：`index.html`、`app.js`、`style.css`（可增子资源，勿出扩展根）。
2. **禁止** 写 Python 布局；宿主已用 WebEngine 加载 `ui/index.html`。
3. 引入 `qrc:///qtwebchannel/qwebchannel.js` 与 `toa_bridge.js`；用 `TOA.ready(fn)` 拿 `toa` 对象。
4. 落盘/状态/完成提示：调用 `toa.dataDir()`、`toa.showSaved(text, path)`、`toa.reportStatus(msg, level)`。
5. 默认 **禁止** 外链脚本；需联网时在 `plugin.toml` `[safety] allow_network = true` 并说明用途。
"""
    web_hint = (
        "**Web 面扩展**：见 HOST_API.md「WebView 桥 API」；改 `ui/` 下 HTML/JS，勿写 Python 布局。"
        if surface == "webview"
        else ""
    )
    entry_note = (
        "宿主加载 `ui/index.html`；Python 入口可忽略。"
        if surface == "webview"
        else f"宿主只加载入口一个文件：`modules/{plugin_id}/{plugin_id}_page.py`。"
    )
    return f"""# TOA3 用户扩展铁律 · {name}

你是 **当前用户 TOA 应用内** 的业务扩展开发代理（对标 skill `toa3-user-extension`）。  
目标：用最短路径做出「能打开、能用」的主功能；**不得研究/改动宿主，不得影响本机其它软件**。

插件根目录（唯一可写工作区）：`{root_hint}`

{isolation_rules_text(plugin_id=plugin_id)}
{web_block}

## 只做业务（省时间）

1. **只实现用户要的功能主路径**，不要做架构调研、不要重构宿主、不要写长篇分析。
2. 开干前 **只读本目录**：`REQUIREMENTS.md`、`AGENTS.md`、`HOST_API.md`、`plugin.toml`、入口文件；**然后直接改**。
3. 需求以 `REQUIREMENTS.md` 为准；不清时只问 **一句**，得到答复后立刻实现。
4. 完成后一句话告诉用户：回 TOA → 顶栏 **系统** → **扩展** → **开发完成** → **打开** → 顶栏 **业务**。

## 导入约定（照做，勿查宿主）

{entry_note}

1. **禁止** `from modules.{plugin_id}...`（那是官方 `modules/`，会加载失败）。
2. 允许 API 见本目录 `HOST_API.md`。
3. **禁止** Read/Grep 任何 TOA 源码路径。

## 界面品质（硬门禁 · surface=qt）

扩展页必须像正式 TOA 功能，**禁止「标题 + 一串全宽输入框」的简陋页**。

{web_hint}

**禁止** `setStyleSheet`；生成完成用 `show_saved` 或 `toa.showSaved`。

## 开发规范

1. surface=qt：页面继承 `BasePage`；控件只来自 `widgets`。  
2. surface=webview：只改 `ui/` 内 HTML/JS/CSS。  
3. 路径用 `module_data_dir` / `module_output_dir` 或桥 `toa.dataDir()`。  
4. 外部 API 只经 `integrations`，且须在 `plugin.toml` 声明。  

## 完成后

用户点「开发完成」→「打开」后出现在侧栏 **业务**；点「移除」可彻底删掉。
"""


def refresh_extension_guard_docs(
    root: Path | str,
    *,
    plugin_id: str = "",
    name: str = "",
) -> None:
    """刷新扩展内 AGENTS.md / HOST_API.md（投喂前调用，堵住「去扫宿主」）。"""
    path = Path(root).expanduser().resolve()
    if not path.is_dir():
        return
    pid = str(plugin_id or path.name).strip() or path.name
    display = str(name or pid).strip() or pid
    try:
        if (path / "plugin.toml").is_file():
            man = parse_plugin_root(path)
            pid = man.plugin_id or pid
            display = man.name or display
            surface = man.entry_surface
        else:
            surface = "qt"
    except Exception:
        surface = "qt"
    (path / "AGENTS.md").write_text(
        agents_markdown(
            plugin_id=pid, name=display, plugin_root=str(path), surface=surface
        ),
        encoding="utf-8",
    )
    (path / "HOST_API.md").write_text(
        host_api_markdown(plugin_id=pid, surface=surface),
        encoding="utf-8",
    )


def user_guide_markdown(*, plugin_id: str, name: str) -> str:
    return f"""# {name} · 使用说明

这是你的 **TOA 扩展**（id: `{plugin_id}`），默认挂在 **业务** 子模块。

## 三步

1. 在智能体里用一句话说你要什么（遵守 `AGENTS.md`）
2. 回 TOA → 顶栏 **系统** → **扩展** → **打开**
3. 顶栏点 **业务**，侧栏打开本功能；不要了点 **移除**

## 安全

- 本扩展只影响你自己的 TOA
- 隐藏或移除不会影响官方功能与智能体
- 不要让智能体修改本目录以外的文件
"""


def plugin_toml_text(
    *,
    plugin_id: str,
    name: str,
    group: str,
    description: str = "",
    order: int = 90,
    surface: str = "qt",
    web_root: str = "ui/index.html",
) -> str:
    class_name = _pascal(plugin_id)
    desc = (description or f"{name}（用户业务插件）").replace('"', '\\"')
    surf = str(surface or "qt").strip().lower()
    if surf not in ("qt", "webview"):
        surf = "qt"
    entry_lines = [
        f'surface = "{surf}"',
        f'web_root = "{web_root}"',
        f'module_path = "modules.{plugin_id}.{plugin_id}_page"',
        f'class_name = "{class_name if surf == "qt" else "WebExtensionHost"}"',
        f'page_id = "{plugin_id}"',
    ]
    entry_block = "\n".join(entry_lines)
    return f'''schema_version = 1

[plugin]
id = "{plugin_id}"
name = "{name}"
group = "{group}"
order = {int(order)}
version = "0.1.0"
requires_license = false
feature_id = ""
author = ""
description = "{desc}"

[entry]
{entry_block}

[storage]
data_key = "{plugin_id}"

[safety]
allow_network = false
allow_shell = false
integrations = []
'''


def page_py_text(*, plugin_id: str, name: str) -> str:
    class_name = _pascal(plugin_id)
    return f'''# -*- coding: utf-8 -*-
"""业务插件页 · {name}（脚手架示范布局，请按需求改内容，保持控件库用法）。"""
from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from core.base_page import BasePage
from core.status_service import StatusLevel
from widgets import (
    DateEdit,
    FormSection,
    HintLabel,
    LineEdit,
    PageHeader,
    PlainTextEdit,
    PrimaryButton,
    ReadOnlyPlainTextEdit,
    ScrollPage,
    SecondaryButton,
    SemanticLabel,
)


class {class_name}(BasePage):
    page_id = "{plugin_id}"
    page_title = "{name}"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollPage()
        outer.addWidget(scroll)

        scroll.add_widget(
            PageHeader(
                "{name}",
                "按分区填写 · 主按钮在操作条 · 短字段勿拉满整行（示范布局，请改成你的业务）。",
            )
        )

        meta = FormSection("基本信息")
        meta.add_widget(HintLabel("日期用 DateEdit；名称等短字段限制最大宽度。"))
        row = QHBoxLayout()
        self._date = DateEdit(date=QDate.currentDate())
        self._date.setMaximumWidth(280)
        row.addWidget(self._date)
        self._title = LineEdit("")
        self._title.setPlaceholderText("标题 / 主题")
        self._title.setMaximumWidth(360)
        row.addWidget(self._title)
        row.addStretch(1)
        meta.add_layout(row)
        scroll.add_widget(meta)

        body = FormSection("正文")
        self._body = PlainTextEdit()
        self._body.setPlaceholderText("在此填写主要内容，每行一条亦可。")
        self._body.setMinimumHeight(140)
        self._body.setMaximumHeight(220)
        body.add_widget(self._body)
        scroll.add_widget(body)

        actions = FormSection("操作")
        ops = QHBoxLayout()
        self._btn_run = PrimaryButton("生成 / 执行")
        self._btn_run.clicked.connect(self._on_run)
        ops.addWidget(self._btn_run)
        btn_clear = SecondaryButton("清空预览")
        btn_clear.clicked.connect(lambda: self._preview.setPlainText(""))
        ops.addWidget(btn_clear)
        ops.addStretch(1)
        self._status = SemanticLabel("就绪", kind="info")
        ops.addWidget(self._status)
        actions.add_layout(ops)
        scroll.add_widget(actions)

        prev = FormSection("预览")
        self._preview = ReadOnlyPlainTextEdit("")
        self._preview.setMinimumHeight(120)
        prev.add_widget(self._preview)
        scroll.add_widget(prev)
        scroll.add_stretch(1)

        self.apply_page_focus_policy()

    def primary_focus_widget(self):
        return self._title

    def focus_tab_widgets(self):
        return [self._date, self._title, self._body, self._btn_run]

    def _on_run(self) -> None:
        title = self._title.text().strip() or "{name}"
        date_s = self._date.date().toString("yyyy-MM-dd")
        body = self._body.toPlainText().strip()
        text = f"# {{title}}\\n\\n日期：{{date_s}}\\n\\n{{body or '（正文为空）'}}\\n"
        self._preview.setPlainText(text)
        self._status.setText("已生成预览")
        self.report_status("脚手架演示完成 · 请按 AGENTS.md 改成真实业务", level=StatusLevel.SUCCESS)
'''


def _extension_web_assets_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "assets" / "extension_web"


def web_index_html(*, plugin_id: str, name: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{name}</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <main class="page">
    <header>
      <h1>{name}</h1>
      <p class="hint">Web 面扩展 · 改 ui/app.js 实现业务 · 宿主桥 TOA.ready</p>
    </header>
    <section id="app"></section>
  </main>
  <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
  <script src="toa_bridge.js"></script>
  <script src="app.js"></script>
</body>
</html>
"""


def web_app_js(*, name: str) -> str:
    return f"""/* {name} · 用户扩展 Web 面入口 */
(function () {{
  "use strict";

  function render(root, toa) {{
    root.innerHTML = ""
      + "<p>扩展 id：<code>" + toa.pluginId() + "</code></p>"
      + "<p>数据目录：<code>" + toa.dataDir() + "</code></p>"
      + "<button type=\\"button\\" id=\\"btn-hello\\">打个招呼</button>";
    document.getElementById("btn-hello").onclick = function () {{
      toa.reportStatus("你好 · {name} 网页扩展已就绪", "success");
    }};
  }}

  TOA.ready(function (toa) {{
    var root = document.getElementById("app");
    if (!root) return;
    render(root, toa);
    var pal = TOA.parsePalette(toa.themePalette());
    if (pal.background) {{
      document.body.style.background = pal.background;
      document.body.style.color = pal.text_primary || "#ccc";
    }}
  }});
}})();
"""


def web_style_css() -> str:
    return """/* 用户扩展 Web 面基础样式（可自由改） */
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
  font-size: 14px;
  line-height: 1.55;
  background: #1e1e1e;
  color: #cccccc;
}
.page { max-width: 720px; margin: 0 auto; padding: 20px 16px 32px; }
h1 { font-size: 20px; margin: 0 0 6px; font-weight: 600; }
.hint { margin: 0 0 16px; opacity: 0.75; font-size: 13px; }
button {
  margin-top: 12px;
  padding: 8px 16px;
  border-radius: 6px;
  border: 1px solid #444;
  background: #2d2d2d;
  color: inherit;
  cursor: pointer;
}
button:hover { background: #383838; }
code { font-size: 12px; word-break: break-all; }
"""


def _write_web_ui_scaffold(root_path: Path, *, plugin_id: str, name: str) -> None:
    ui = root_path / "ui"
    ui.mkdir(parents=True, exist_ok=True)
    (ui / "index.html").write_text(web_index_html(plugin_id=plugin_id, name=name), encoding="utf-8")
    (ui / "app.js").write_text(web_app_js(name=name), encoding="utf-8")
    (ui / "style.css").write_text(web_style_css(), encoding="utf-8")
    bridge_src = _extension_web_assets_dir() / "toa_bridge.js"
    if bridge_src.is_file():
        (ui / "toa_bridge.js").write_text(bridge_src.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        (ui / "toa_bridge.js").write_text("// TOA bridge missing\n", encoding="utf-8")


def create_plugin_scaffold(
    root: Path | str | None = None,
    *,
    plugin_id: str,
    name: str,
    group: str = "business",
    description: str = "",
    order: int = 90,
    surface: str = "qt",
    overwrite: bool = False,
) -> Path:
    """在安全目录写入契约与空页；默认 data/user/extensions/<id>。"""
    from services.plugin_sandbox import (
        assert_registerable_root,
        default_plugin_root,
        is_app_source_or_install_code,
        is_bundled_sample,
    )

    pid = str(plugin_id or "").strip()
    if not _ID_RE.match(pid):
        raise ValueError("plugin_id 须为小写 snake_case（字母开头）")
    if pid in MIGRATED_MODULES:
        raise ValueError(f"id「{pid}」与内置模块冲突")
    g = str(group or "business").strip().lower()
    if g not in GROUP_ORDER:
        raise ValueError(f"group 须为 {GROUP_ORDER} 之一")
    surf = str(surface or "qt").strip().lower()
    if surf not in ("qt", "webview"):
        raise ValueError("surface 须为 qt 或 webview")

    root_path = Path(root).expanduser().resolve() if root else default_plugin_root(pid)
    if is_app_source_or_install_code(root_path) and not is_bundled_sample(root_path):
        raise ValueError(
            "禁止在 TOA 源码/安装目录创建扩展。请使用本机扩展区（默认已选）。"
        )
    # 父目录若已存在则校验可登记
    parent = root_path.parent
    if parent.is_dir() and not is_bundled_sample(root_path):
        # 允许在 user_extensions 下新建子目录；父目录本身须安全
        if is_app_source_or_install_code(parent):
            raise ValueError(
                "禁止在 TOA 源码/安装目录创建扩展。请使用本机扩展区（默认已选）。"
            )

    root_path.mkdir(parents=True, exist_ok=True)

    man_path = root_path / "plugin.toml"
    if man_path.is_file() and not overwrite:
        parse_plugin_root(root_path)
        return root_path

    pkg = root_path / "modules" / pid
    page_file = pkg / f"{pid}_page.py"
    if surf == "qt":
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "__init__.py").write_text("# -*- coding: utf-8 -*-\n", encoding="utf-8")
        if page_file.is_file() and not overwrite:
            raise ValueError(f"已存在 {page_file}，如需重建请勾选覆盖")

    display = str(name or pid).strip() or pid
    man_path.write_text(
        plugin_toml_text(
            plugin_id=pid,
            name=display,
            group=g,
            description=description,
            order=order,
            surface=surf,
        ),
        encoding="utf-8",
    )
    (root_path / "AGENTS.md").write_text(
        agents_markdown(
            plugin_id=pid, name=display, plugin_root=str(root_path), surface=surf
        ),
        encoding="utf-8",
    )
    (root_path / "HOST_API.md").write_text(
        host_api_markdown(plugin_id=pid, surface=surf),
        encoding="utf-8",
    )
    (root_path / "README.md").write_text(
        user_guide_markdown(plugin_id=pid, name=display),
        encoding="utf-8",
    )
    if surf == "qt":
        page_file.write_text(page_py_text(plugin_id=pid, name=display), encoding="utf-8")
    else:
        _write_web_ui_scaffold(root_path, plugin_id=pid, name=display)
    parse_plugin_root(root_path)
    return root_path
