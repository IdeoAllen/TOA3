# -*- coding: utf-8 -*-
"""记事预览：含 ```mermaid 时用本机 mermaid.min.js 出图。"""
from __future__ import annotations

import html as html_lib
import re
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QTextDocument

_FENCE = re.compile(r"```\s*mermaid\s*\n([\s\S]*?)```", re.IGNORECASE)
_ROOT = Path(__file__).resolve().parents[2]
_MERMAID_JS = _ROOT / "resources" / "notepad" / "mermaid.min.js"


def has_mermaid(md: str) -> bool:
    return bool(_FENCE.search(md or ""))


def mermaid_js_path() -> Path:
    return _MERMAID_JS


def extract_mermaid_blocks(md: str) -> list[str]:
    return [m.group(1).strip() for m in _FENCE.finditer(md or "") if (m.group(1) or "").strip()]


def _md_without_mermaid_as_html(md: str) -> str:
    """非 mermaid 段走 Qt Markdown→HTML；mermaid 段换成占位 div。"""
    parts: list[str] = []
    last = 0
    idx = 0
    for m in _FENCE.finditer(md or ""):
        before = (md or "")[last : m.start()]
        if before.strip():
            doc = QTextDocument()
            doc.setMarkdown(before)
            parts.append(doc.toHtml())
        body = html_lib.escape(m.group(1) or "")
        parts.append(
            f'<div class="mermaid" id="toa-mmd-{idx}">\n{body}\n</div>'
        )
        idx += 1
        last = m.end()
    tail = (md or "")[last:]
    if tail.strip():
        doc = QTextDocument()
        doc.setMarkdown(tail)
        parts.append(doc.toHtml())
    return "\n".join(parts) if parts else "<p></p>"


def build_mermaid_preview_html(md: str) -> str:
    """完整 HTML 文档：正文 + 本机 mermaid 脚本。"""
    from modules.quick_notepad.md_text import prepare_markdown_for_preview

    prepared = prepare_markdown_for_preview(md or "")
    body_html = _md_without_mermaid_as_html(prepared)
    js_uri = QUrl.fromLocalFile(str(_MERMAID_JS.resolve())).toString()
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<style>
body {{ font-family: "Microsoft YaHei UI", sans-serif; font-size: 11pt;
  color: #1f2937; margin: 16px; line-height: 1.55; background: #fff; }}
.mermaid {{ margin: 12px 0; text-align: center; }}
pre, code {{ font-family: Consolas, monospace; }}
table {{ border-collapse: collapse; }}
th, td {{ border: 1px solid #cbd5e1; padding: 4px 8px; }}
</style>
</head><body>
{body_html}
<script src="{js_uri}"></script>
<script>
mermaid.initialize({{ startOnLoad: true, theme: "neutral", securityLevel: "loose" }});
</script>
</body></html>
"""


def schematic_for_mermaid(block_id: str) -> str:
    """兼容旧调用；组件卡已改用 ChartSchematic 绘制样子。"""
    schematics = {
        "mermaid_flow": "流程图 · 纵向",
        "mermaid_lr": "流程图 · 横向",
        "mermaid_seq": "时序图",
        "mermaid_pie": "饼图",
        "mermaid_gantt": "甘特图",
    }
    return schematics.get(block_id, "图表")
