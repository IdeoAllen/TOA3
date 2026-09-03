# -*- coding: utf-8 -*-
"""所见即所得正文：HTML 存盘；兼容旧 Markdown / 纯文本。"""
from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QImage, QTextDocument, QTextImageFormat
from PySide6.QtWidgets import QTextEdit

from services.storage_paths import module_data_dir

_HTML_HINT = re.compile(
    r"<!DOCTYPE\s+html|<html[\s>]|<body[\s>]|<p[\s>]|<div[\s>]|<img[\s>]|<h[1-6][\s>]",
    re.IGNORECASE,
)


def looks_like_html(text: str) -> bool:
    s = (text or "").lstrip()
    if not s:
        return False
    if s.startswith("<!--toa-html-->"):
        return True
    return bool(_HTML_HINT.search(s[:800]))


def images_dir() -> Path:
    d = module_data_dir("quick_notepad", create=True) / "images"
    d.mkdir(parents=True, exist_ok=True)
    return d


def markdown_demo_template() -> str:
    """多功能模式新建默认正文：Markdown 语法全景示例（可整段删除后开写）。"""
    return """# TOA 快速记事 · Markdown 全景示例

> 本页演示常用 Markdown 写法。点上方 **源码 / 设计 / 预览** 页签切换；**全屏** 专注写作。全选删除即可开写。

---

## 1. 强调与颜色语义

**加粗重点** · *斜体补充* · ~~已完成划掉~~ · `行内代码`

普通段落里混排 **会议结论** 与 *待确认事项*，适合会议纪要速记。

---

## 2. 列表与待办

### 无序列表

- 收集素材与背景
- 整理参会人名单
  - 业务方
  - 技术方
- 输出行动项

### 有序列表

1. 开场对齐目标
2. 逐项过议题
3. 确认责任人与截止时间

### 任务清单

- [x] 已完成：定会议室
- [ ] 待办：发纪要
- [ ] 待办：跟进采购流程

---

## 3. 引用与提示

> 引用块适合放领导原话、客户反馈或规范摘录。
>
> 多行引用会自动合并成一块，便于和正文区分。

---

## 4. 代码

行内：`python -m app.main` 或 `git status`

块级：

```python
def summarize(items: list[str]) -> str:
    return "\\n".join(f"- {x}" for x in items)
```

```bash
# 打包前自检
python scripts/audit_migration.py
```

---

## 5. 表格

| 模块 | 负责人 | 状态 | 备注 |
| --- | --- | --- | --- |
| 剪贴板历史 | 张三 | 进行中 | Wave★ |
| 截图工具 | 李四 | 已完成 | 热键已验 |
| 快速记事 | 王五 | 联调 | 本页 |

---

## 6. 链接与分隔

- 官网：[一舟科技](https://www.yczh.tech)
- 文档：<https://docs.example.com/guide>

---

## 7. 分步计划（示例）

### 阶段 A · 今天

1. 清空本模板，写下真实标题
2. 用 **Tab** 在大纲里降级子项
3. `Ctrl+S` 或等自动保存

### 阶段 B · 本周

- 把剪贴板内容 **从剪贴板** 落入正文
- 截图完成后粘贴图片（多功能模式）
- 需要时用 **导入 MD** 拉本地文件

---

## 8. 分割线

上文是结构示例，下面开始你的正文。

---

写在这里 👇
"""


def refresh_markdown_preview(source: QTextEdit, preview: QTextEdit) -> None:
    """源码 → 预览（Qt 内置 Markdown 渲染）。"""
    text = source.toPlainText()
    preview.blockSignals(True)
    try:
        if not text.strip():
            preview.clear()
        else:
            preview.setMarkdown(text)
    finally:
        preview.blockSignals(False)


def sync_markdown_to_design(source: QTextEdit, design: QTextEdit) -> None:
    """Markdown 源码 → 所见即所得设计区。"""
    load_body_into(design, source.toPlainText())


def sync_design_to_markdown(design: QTextEdit, source: QTextEdit) -> None:
    """设计区 → Markdown 源码（尽量保留结构）。"""
    text = ""
    try:
        text = design.toMarkdown()
    except Exception:
        text = design.toPlainText()
    source.blockSignals(True)
    try:
        source.setPlainText(text)
    finally:
        source.blockSignals(False)


def refresh_editor_preview(
    *,
    source: QTextEdit,
    preview: QTextEdit,
    design: QTextEdit | None = None,
    prefer_design: bool = False,
) -> None:
    """预览：Markdown 走源码；富文本/HTML 走设计区渲染。"""
    preview.blockSignals(True)
    try:
        if prefer_design and design is not None and design.toPlainText().strip():
            preview.setHtml(design.toHtml())
            return
        refresh_markdown_preview(source, preview)
    finally:
        preview.blockSignals(False)


def rich_has_images(edit: QTextEdit) -> bool:
    doc = edit.document()
    if doc is None:
        return False
    return bool(doc.toHtml().lower().find("<img") >= 0)


def rich_starter_template() -> str:
    """多功能模式「新建」默认正文：多样式示例 + 工具对照，可整段删掉后开写。"""
    return """<!--toa-html-->
<html><head><meta charset="utf-8"/></head><body>
<h1 style="color:#1D4ED8;margin-bottom:4px;">写下一个好想法</h1>
<p style="color:#64748B;font-size:10.5pt;margin-top:0;">
选中文字，用上方工具栏排版。本页是新建示例，可全选删除后开写。
</p>

<h2 style="color:#0F766E;">今日要点</h2>
<ul>
<li><span style="background-color:#FEF08A;">高亮</span> 最重要的一件事</li>
<li><b>加粗</b> · <i>斜体</i> · <u>下划线</u> · <s>已划掉</s></li>
<li><span style="color:#DC2626;">红色强调</span>
 · <span style="color:#2563EB;">蓝色标注</span>
 · <span style="color:#7C3AED;">紫色备注</span></li>
</ul>

<h3 style="color:#B45309;">分步计划</h3>
<ol>
<li>收集素材与要点</li>
<li>整理成清晰结构</li>
<li>收尾检查并导出</li>
</ol>

<p style="background-color:#F0F9FF;color:#0369A1;">
小贴士：用「字色 / 高亮」给关键词上色；「图片」插入截图；「链接」挂网址。
</p>

<p>参考：<a href="https://">在此粘贴网址</a></p>

<p style="margin-top:20px;margin-bottom:4px;padding:8px 10px;background-color:#F8FAFC;border-left:3px solid #94A3B8;">
<span style="color:#334155;font-size:11pt;"><b>工具对照</b></span>
<span style="color:#64748B;font-size:10pt;">　对照上文，各样式对应工具栏</span>
</p>
<p style="margin:4px 0;color:#475569;font-size:10pt;">
<span style="color:#1D4ED8;font-size:13pt;"><b>写下一个好想法</b></span>
　→　标题 1（H1，自带蓝色）
</p>
<p style="margin:4px 0;color:#475569;font-size:10pt;">
<span style="color:#0F766E;font-size:12pt;"><b>今日要点</b></span>
　→　标题 2（H2）
</p>
<p style="margin:4px 0;color:#475569;font-size:10pt;">
<span style="color:#B45309;font-size:11pt;"><b>分步计划</b></span>
　→　标题 3（H3）
</p>
<p style="margin:4px 0;color:#475569;font-size:10pt;">
<span style="background-color:#FEF08A;">高亮</span>
　→　高亮（选黄底）
</p>
<p style="margin:4px 0;color:#475569;font-size:10pt;">
<b>加粗</b> · <i>斜体</i> · <u>下划线</u> · <s>已划掉</s>
　→　B / I / U / S
</p>
<p style="margin:4px 0;color:#475569;font-size:10pt;">
<span style="color:#DC2626;">红色强调</span>
 · <span style="color:#2563EB;">蓝色标注</span>
 · <span style="color:#7C3AED;">紫色备注</span>
　→　字色
</p>
<p style="margin:4px 0;color:#475569;font-size:10pt;">
圆点列表 · 编号列表
　→　圆点 / 编号
</p>
<p style="margin:4px 0;color:#475569;font-size:10pt;">
<a href="https://">在此粘贴网址</a>
　→　链接
</p>
<p style="margin:4px 0;color:#475569;font-size:10pt;">
<span style="background-color:#F0F9FF;color:#0369A1;">浅蓝提示段</span>
　→　普通段落 + 字色（青）+ 高亮（浅蓝底）
</p>
<p style="margin:8px 0 4px 0;color:#64748B;font-size:9.5pt;">
清除　→　去掉样式；　图片　→　插入本地图；　只要颜色不要变大　→　只用字色
</p>

<p style="color:#94A3B8;font-size:9.5pt;margin-top:16px;">— 快速记事 · 多功能模板 —</p>
</body></html>
"""


def load_body_into(edit: QTextEdit, body: str) -> None:
    """把存盘正文载入富文本框（HTML / Markdown / 纯文本）。"""
    text = body or ""
    edit.blockSignals(True)
    try:
        if not text.strip():
            edit.clear()
        elif looks_like_html(text):
            raw = text
            if raw.startswith("<!--toa-html-->"):
                raw = raw[len("<!--toa-html-->") :].lstrip()
            edit.setHtml(raw)
        else:
            try:
                edit.setMarkdown(text)
            except Exception:
                edit.setPlainText(text)
    finally:
        edit.blockSignals(False)


def export_body_from(edit: QTextEdit) -> str:
    """富文本 → 存盘（HTML，便于图片与格式）。"""
    html = edit.toHtml()
    if not edit.toPlainText().strip():
        return ""
    return "<!--toa-html-->\n" + html


def store_image_file(src: Path, *, max_width: int = 960) -> Path:
    """复制图片到记事数据目录，过大则缩小。"""
    src = Path(src)
    suffix = src.suffix.lower() or ".png"
    if suffix not in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}:
        suffix = ".png"
    dest = images_dir() / f"{uuid.uuid4().hex}{suffix}"
    img = QImage(str(src))
    if img.isNull():
        shutil.copy2(src, dest)
        return dest
    if img.width() > max_width:
        img = img.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)
    if not img.save(str(dest)):
        shutil.copy2(src, dest)
    return dest


def insert_image(edit: QTextEdit, image_path: Path) -> bool:
    dest = store_image_file(Path(image_path))
    return _insert_stored_image(edit, dest)


def insert_qimage(edit: QTextEdit, qimg: QImage, *, max_width: int = 960) -> bool:
    """把内存位图写入记事图库并插入光标处。"""
    if qimg is None or qimg.isNull():
        return False
    img = qimg
    if img.width() > max_width:
        img = img.scaledToWidth(max_width, Qt.TransformationMode.SmoothTransformation)
    dest = images_dir() / f"{uuid.uuid4().hex}.png"
    if not img.save(str(dest), "PNG"):
        return False
    return _insert_stored_image(edit, dest)


def _insert_stored_image(edit: QTextEdit, dest: Path) -> bool:
    img = QImage(str(dest))
    if img.isNull():
        return False
    url = QUrl.fromLocalFile(str(dest.resolve()))
    doc = edit.document()
    doc.addResource(QTextDocument.ResourceType.ImageResource, url, img)
    fmt = QTextImageFormat()
    fmt.setName(url.toString())
    # 初始宽度适配编辑区，便于设计模式拖角继续缩放
    try:
        max_w = max(160, min(960, edit.viewport().width() - 48))
    except Exception:
        max_w = 640
    if img.width() > max_w > 0:
        h = max(1, int(round(img.height() * max_w / img.width())))
        fmt.setWidth(max_w)
        fmt.setHeight(h)
    cur = edit.textCursor()
    cur.insertImage(fmt)
    edit.setTextCursor(cur)
    return True
