# -*- coding: utf-8 -*-
"""记事组件：常用文字标记 + 图表（Mermaid）分组；卡片直观、拖入辅助编码。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QByteArray, QMimeData, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QTextEdit

MIME_BLOCK = "application/x-toa-notepad-block"


@dataclass(frozen=True)
class BlockSpec:
    id: str
    title: str
    hint: str
    preview: str
    html: str = ""
    group: str = "常用"
    toolbar: str = ""
    markdown: str = ""
    surface: str = "md"


_MD: dict[str, str] = {
    "h1": "# 写下一个好想法\n",
    "h2": "## 今日要点\n",
    "h3": "### 分步计划\n",
    "h4": "#### 小节标题\n",
    "h5": "##### 细目\n",
    "h6": "###### 备注级标题\n",
    "bold": "**加粗文字**\n",
    "italic": "*斜体文字*\n",
    "strike": "~~删除线文字~~\n",
    "highlight": "==高亮重点==\n",
    "bullets": "- 第一点（改成你的内容）\n- 第二点\n- 第三点\n",
    "steps": "1. 准备\n2. 执行\n3. 收尾检查\n",
    "quote": "> 在此粘贴需要引用的原话或规范摘录。\n",
    "inline_code": "`行内代码`\n",
    "code_block": "```\ndef hello():\n    print(\"改成你的代码\")\n```\n",
    "hr": "---\n",
    "table": (
        "| 模块 | 负责人 | 状态 |\n"
        "| --- | --- | --- |\n"
        "| 项目 A | — | 进行中 |\n"
        "| 项目 B | — | 待开始 |\n"
    ),
    "checklist": "- [ ] 待办事项一\n- [ ] 待办事项二\n- [x] 已完成示例\n",
    "link": "[点此填写网址](https://www.yczh.tech)\n",
    "image": "![图片说明](about:blank)\n",
    "icon": '<img src="about:blank" width="48" alt="图标" />\n',
    "mermaid_flow": (
        "```mermaid\n"
        "flowchart TD\n"
        "  A[开始] --> B[处理]\n"
        "  B --> C{判断}\n"
        "  C -->|是| D[完成]\n"
        "  C -->|否| B\n"
        "```\n"
    ),
    "mermaid_lr": (
        "```mermaid\n"
        "flowchart LR\n"
        "  A[输入] --> B[加工] --> C[输出]\n"
        "```\n"
    ),
    "mermaid_seq": (
        "```mermaid\n"
        "sequenceDiagram\n"
        "  participant U as 用户\n"
        "  participant S as 系统\n"
        "  U->>S: 提交请求\n"
        "  S-->>U: 返回结果\n"
        "```\n"
    ),
    "mermaid_pie": (
        "```mermaid\n"
        "pie title 占比示例\n"
        "  \"完成\" : 45\n"
        "  \"进行中\" : 30\n"
        "  \"待开始\" : 25\n"
        "```\n"
    ),
    "mermaid_gantt": (
        "```mermaid\n"
        "gantt\n"
        "  title 计划示例\n"
        "  dateFormat  YYYY-MM-DD\n"
        "  section 阶段\n"
        "  筹备           :a1, 2026-01-01, 7d\n"
        "  执行           :a2, after a1, 14d\n"
        "  收尾           :a3, after a2, 5d\n"
        "```\n"
    ),
}

BLOCKS: tuple[BlockSpec, ...] = (
    BlockSpec("h1", "标题 H1", "#", "写下一个好想法", toolbar="H1", group="常用"),
    BlockSpec("h2", "标题 H2", "##", "今日要点", toolbar="H2", group="常用"),
    BlockSpec("h3", "标题 H3", "###", "分步计划", toolbar="H3", group="常用"),
    BlockSpec("h4", "标题 H4", "####", "小节标题", toolbar="H4", group="常用"),
    BlockSpec("h5", "标题 H5", "#####", "细目", toolbar="H5", group="常用"),
    BlockSpec("h6", "标题 H6", "######", "备注级", toolbar="H6", group="常用"),
    BlockSpec("bold", "加粗", "**…**", "加粗文字", toolbar="B", group="常用"),
    BlockSpec("italic", "斜体", "*…*", "斜体文字", toolbar="I", group="常用"),
    BlockSpec("strike", "删除线", "~~…~~", "删除线文字", toolbar="S", group="常用"),
    BlockSpec("highlight", "高亮", "==…==", "高亮重点", toolbar="高亮", group="常用"),
    BlockSpec("bullets", "项目符号", "-", "无序列表", toolbar="•", group="常用"),
    BlockSpec("steps", "编号列表", "1.", "有序列表", toolbar="1.", group="常用"),
    BlockSpec("quote", "引用", ">", "规范摘录", toolbar="引用", group="常用"),
    BlockSpec("inline_code", "行内代码", "`…`", "行内代码", toolbar="`", group="常用"),
    BlockSpec("code_block", "代码块", "```", "代码围栏", toolbar="代码", group="常用"),
    BlockSpec("hr", "分割线", "---", "分割线", toolbar="—", group="常用"),
    BlockSpec("table", "表格", "表", "三列表", toolbar="表格", group="常用"),
    BlockSpec("checklist", "待办清单", "- [ ]", "复选列表", toolbar="待办", group="常用"),
    BlockSpec("link", "链接", "[]()", "链接", toolbar="链接", group="常用"),
    BlockSpec("image", "图片", "![]()", "中图 · 可改大小", toolbar="图片", group="常用"),
    BlockSpec("icon", "图标", "图标", "小图标 · 可改大小", toolbar="图标", group="常用"),
    BlockSpec("time", "时间", "时间戳", "当前时间", toolbar="时间", group="常用"),
    BlockSpec(
        "mermaid_flow", "流程图 TD", "flowchart TD", "纵向流程",
        group="图表", toolbar="",
    ),    BlockSpec(
        "mermaid_lr", "流程图 LR", "flowchart LR", "横向流程",
        group="图表", toolbar="",
    ),
    BlockSpec(
        "mermaid_seq", "时序图", "sequenceDiagram", "请求/响应",
        group="图表", toolbar="",
    ),
    BlockSpec(
        "mermaid_pie", "饼图", "pie", "占比",
        group="图表", toolbar="",
    ),
    BlockSpec(
        "mermaid_gantt", "甘特图", "gantt", "计划条",
        group="图表", toolbar="",
    ),
)

_BY_ID: dict[str, BlockSpec] = {b.id: b for b in BLOCKS}
GROUP_ORDER = ("常用", "图表")


def blocks_by_group(surface: str = "md") -> list[tuple[str, tuple[BlockSpec, ...]]]:
    surf = "md" if str(surface or "").strip().lower() != "html" else "html"
    if surf != "md":
        return []
    buckets: dict[str, list[BlockSpec]] = {g: [] for g in GROUP_ORDER}
    for b in BLOCKS:
        g = b.group if b.group in buckets else "常用"
        buckets[g].append(b)
    return [(g, tuple(buckets[g])) for g in GROUP_ORDER if buckets[g]]


def get_block(block_id: str) -> BlockSpec | None:
    return _BY_ID.get(str(block_id or "").strip())


def is_chart_block(block_id: str) -> bool:
    spec = get_block(block_id)
    return bool(spec and spec.group == "图表")


def is_h5_block(block_id: str) -> bool:
    return False


def mime_for_block(block_id: str) -> QMimeData | None:
    spec = get_block(block_id)
    if spec is None:
        return None
    md = QMimeData()
    md.setData(MIME_BLOCK, QByteArray(spec.id.encode("utf-8")))
    piece = markdown_for_block(block_id)
    md.setText(piece or (spec.preview or ""))
    return md


def block_id_from_mime(source) -> str | None:
    if source is None or not source.hasFormat(MIME_BLOCK):
        return None
    raw = bytes(source.data(MIME_BLOCK)).decode("utf-8", errors="ignore").strip()
    return raw if raw in _BY_ID else None


def insert_html_block(edit: QTextEdit, html: str) -> bool:
    return False


def is_markdown_block(block_id: str) -> bool:
    return bool(markdown_for_block(block_id).strip())


_HTML_IN_MD = re.compile(r"</?[a-zA-Z][^>]*>")


def _pure_markdown(text: str) -> str:
    raw = text or ""
    if _HTML_IN_MD.search(raw):
        raw = _HTML_IN_MD.sub("", raw)
    return raw


def markdown_for_block(block_id: str) -> str:
    bid = str(block_id or "").strip()
    if bid == "time":
        return _pure_markdown(datetime.now().strftime("%Y-%m-%d %H:%M") + "\n")
    spec = get_block(bid)
    if spec is None:
        return ""
    if (spec.markdown or "").strip():
        return _pure_markdown((spec.markdown or "").strip() + "\n")
    templ = _MD.get(spec.id)
    if templ and templ.strip():
        # mermaid / 图标 HTML 宽度属性保留
        if spec.id.startswith("mermaid_") or spec.id in ("icon",):
            return templ if templ.endswith("\n") else templ + "\n"
        return _pure_markdown(templ)
    title = (spec.title or spec.preview or bid or "内容").strip()
    return _pure_markdown(f"# {title}\n")


def insert_markdown_snippet(edit, markdown: str, *, at_end: bool = False) -> bool:
    if edit is None or not hasattr(edit, "textCursor") or edit.isReadOnly():
        return False
    piece = (markdown or "").strip("\n")
    if not piece:
        return False
    piece = piece + "\n"
    cur = edit.textCursor()
    cur.beginEditBlock()
    try:
        if at_end:
            cur.movePosition(QTextCursor.MoveOperation.End)
            if cur.position() > 0 and not cur.atBlockStart():
                block_text = cur.block().text() if cur.block() is not None else ""
                if block_text.strip():
                    cur.insertText("\n")
        elif not cur.atBlockStart() and cur.block().text().strip():
            cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            cur.insertText("\n")
        cur.insertText(piece)
        edit.setTextCursor(cur)
        edit.ensureCursorVisible()
        if hasattr(edit, "setFocus"):
            edit.setFocus(Qt.FocusReason.OtherFocusReason)
    finally:
        cur.endEditBlock()
    return True


def insert_block(edit: QTextEdit, block_id: str) -> bool:
    if get_block(block_id) is None:
        return False
    return insert_markdown_snippet(edit, markdown_for_block(block_id), at_end=True)
