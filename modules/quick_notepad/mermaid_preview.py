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


_BODY_INNER = re.compile(r"<body\b[^>]*>(.*)</body>", re.IGNORECASE | re.DOTALL)


def _palette() -> dict:
    try:
        from app.app_state import AppState

        pal = AppState.get().palette or {}
        return dict(pal) if isinstance(pal, dict) else {}
    except Exception:
        return {}


def _color(pal: dict, key: str, fallback: str) -> str:
    raw = str(pal.get(key) or "").strip()
    if raw.startswith("#") and len(raw) in (4, 7, 9):
        return raw
    return fallback


def _luminance(hex_color: str) -> float:
    raw = (hex_color or "#ffffff").lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    try:
        r = int(raw[0:2], 16)
        g = int(raw[2:4], 16)
        b = int(raw[4:6], 16)
    except ValueError:
        return 255.0
    return 0.299 * r + 0.587 * g + 0.114 * b


def _fragment(html: str) -> str:
    raw = (html or "").strip()
    m = _BODY_INNER.search(raw)
    if not m:
        return raw or "<p></p>"
    inner = (m.group(1) or "").strip()
    return inner or "<p></p>"


_QUOTE_P = re.compile(
    r'<p\b[^>]*style="[^"]*margin-left:\s*40px;\s*margin-right:\s*40px;[^"]*"[^>]*>(.*?)</p>',
    re.IGNORECASE | re.DOTALL,
)
_STYLE_ATTR = re.compile(r'\sstyle="[^"]*"', re.IGNORECASE)
_CALLOUT_LEAD = re.compile(
    r"^\s*\[!(NOTE|TIP|WARNING|IMPORTANT|CAUTION|INFO)\]\s*",
    re.IGNORECASE,
)


def _merge_quote_runs(html: str) -> str:
    """Qt 把引用收成左右各缩进 40px 的段落；收成引用块 / 提示块。"""
    matches = list(_QUOTE_P.finditer(html or ""))
    if not matches:
        return html
    out: list[str] = []
    cursor = 0
    i = 0
    while i < len(matches):
        start = matches[i].start()
        group = [matches[i]]
        j = i + 1
        while j < len(matches):
            gap = html[group[-1].end() : matches[j].start()]
            if gap.strip():
                break
            group.append(matches[j])
            j += 1
        out.append(html[cursor:start])
        bodies = [re.sub(r"\s+", " ", (m.group(1) or "")).strip() for m in group]
        lead = _CALLOUT_LEAD.match(re.sub(r"<[^>]+>", "", bodies[0] or ""))
        kind = ""
        if lead:
            kind = lead.group(1).lower()
            bodies[0] = _CALLOUT_LEAD.sub("", re.sub(r"<[^>]+>", "", bodies[0])).strip()
            # 第一段若只剩标记，丢掉空段
            if not bodies[0]:
                bodies = bodies[1:]
        inner = "".join(f"<p>{b}</p>" for b in bodies if b)
        if not inner:
            inner = "<p></p>"
        if kind:
            label = {
                "note": "说明",
                "info": "说明",
                "tip": "提示",
                "warning": "注意",
                "important": "重要",
                "caution": "小心",
            }.get(kind, "说明")
            cls = "warning" if kind in ("warning", "caution") else "tip" if kind == "tip" else "note"
            out.append(
                f'<blockquote class="callout {cls}"><div class="label">{label}</div>{inner}</blockquote>'
            )
        else:
            out.append(f"<blockquote>{inner}</blockquote>")
        cursor = group[-1].end()
        i = j
    out.append(html[cursor:])
    return "".join(out)


def _upgrade_tables(html: str) -> str:
    def _one(m: re.Match[str]) -> str:
        inner = m.group(1) or ""
        rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", inner, flags=re.IGNORECASE | re.DOTALL)
        if not rows:
            return m.group(0)
        head_cells = re.findall(r"<td\b[^>]*>(.*?)</td>", rows[0], flags=re.IGNORECASE | re.DOTALL)
        thead = "".join(f"<th>{c}</th>" for c in head_cells)
        body_rows = []
        for row in rows[1:]:
            cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, flags=re.IGNORECASE | re.DOTALL)
            body_rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
        body = "".join(body_rows)
        return f"<table><thead><tr>{thead}</tr></thead><tbody>{body}</tbody></table>"

    return re.sub(r"<table\b[^>]*>(.*?)</table>", _one, html or "", flags=re.IGNORECASE | re.DOTALL)


def _upgrade_tasks(html: str) -> str:
    def _li(m: re.Match[str]) -> str:
        inner = m.group(1) or ""
        plain = re.sub(r"<[^>]+>", "", inner).strip()
        if plain.startswith("☑"):
            text = plain[1:].strip()
            return f'<li class="task done"><span class="box"></span>{text}</li>'
        if plain.startswith("☐"):
            text = plain[1:].strip()
            return f'<li class="task"><span class="box"></span>{text}</li>'
        return m.group(0)

    return re.sub(r"<li\b[^>]*>(.*?)</li>", _li, html or "", flags=re.IGNORECASE | re.DOTALL)


def _semanticize_spans(html: str) -> str:
    """行内样式收成 strong / em / s / mark / code，去 style 后效果还在。"""
    span_re = re.compile(r"<span\b([^>]*)>(.*?)</span>", re.IGNORECASE | re.DOTALL)
    code_family = re.compile(
        r"font-family:[^;]*?(Courier|Cascadia|Consolas|monospace)",
        re.IGNORECASE,
    )

    def _repl(m: re.Match[str]) -> str:
        attrs = m.group(1) or ""
        inner = m.group(2) or ""
        style_m = re.search(r'style="([^"]*)"', attrs, re.IGNORECASE)
        style = style_m.group(1) if style_m else ""
        tags: list[str] = []
        if re.search(r"font-weight:\s*(700|bold)", style, re.IGNORECASE):
            tags.append("strong")
        if re.search(r"font-style:\s*italic", style, re.IGNORECASE):
            tags.append("em")
        if "line-through" in style:
            tags.append("s")
        if re.search(r"background-color:\s*#fef08a", style, re.IGNORECASE):
            tags.append("mark")
        out = inner
        for tag in tags:
            out = f"<{tag}>{out}</{tag}>"
        if code_family.search(style):
            out = f"<code>{out}</code>"
        return out

    cur = html or ""
    for _ in range(6):
        nxt = span_re.sub(_repl, cur)
        if nxt == cur:
            break
        cur = nxt
    return cur


_ONE_PRE = re.compile(
    r"<pre\b[^>]*>\s*(.*?)\s*</pre>",
    re.IGNORECASE | re.DOTALL,
)


def _merge_code_fences(html: str) -> str:
    """Qt 把围栏拆成多段 pre；合成一块并保留换行。"""
    matches = list(_ONE_PRE.finditer(html or ""))
    if not matches:
        return html
    out: list[str] = []
    cursor = 0
    i = 0
    while i < len(matches):
        group = [matches[i]]
        j = i + 1
        while j < len(matches):
            gap = (html or "")[group[-1].end() : matches[j].start()]
            if gap.strip():
                break
            group.append(matches[j])
            j += 1
        out.append((html or "")[cursor : group[0].start()])
        lines: list[str] = []
        for m in group:
            text = m.group(1) or ""
            text = re.sub(r"</?code>", "", text, flags=re.IGNORECASE)
            text = re.sub(r"</?span\b[^>]*>", "", text, flags=re.IGNORECASE)
            lines.append(text)
        out.append("<pre><code>" + "\n".join(lines) + "</code></pre>")
        cursor = group[-1].end()
        i = j
    out.append((html or "")[cursor:])
    return "".join(out)


def _polish_reading_html(html: str) -> str:
    """去掉 Qt 行内样式，改成阅读排版可接管的结构；行内标记改成语义标签。"""
    raw = html or ""
    raw = _merge_quote_runs(raw)
    raw = _semanticize_spans(raw)
    raw = _merge_code_fences(raw)
    raw = _upgrade_tables(raw)
    raw = _upgrade_tasks(raw)
    raw = _STYLE_ATTR.sub("", raw)
    raw = re.sub(r"\sborder=\"1\"", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\scellpadding=\"\d+\"", "", raw, flags=re.IGNORECASE)
    raw = raw.replace("</code></code></pre>", "</code></pre>")
    raw = re.sub(r"<p>\s*<br\s*/?>\s*</p>", "", raw, flags=re.IGNORECASE)
    return raw


def _md_segment_html(md: str) -> str:
    piece = (md or "").strip()
    if not piece:
        return ""
    doc = QTextDocument()
    doc.setMarkdown(piece)
    return _polish_reading_html(_fragment(doc.toHtml()))


def _md_without_mermaid_as_html(md: str) -> str:
    """非 mermaid 段走 Qt Markdown→HTML；mermaid 段换成占位 div。"""
    parts: list[str] = []
    last = 0
    idx = 0
    for m in _FENCE.finditer(md or ""):
        before = (md or "")[last : m.start()]
        frag = _md_segment_html(before)
        if frag:
            parts.append(frag)
        body = html_lib.escape(m.group(1) or "")
        parts.append(f'<div class="mermaid" id="toa-mmd-{idx}">\n{body}\n</div>')
        idx += 1
        last = m.end()
    tail = (md or "")[last:]
    frag = _md_segment_html(tail)
    if frag:
        parts.append(frag)
    if not parts and (md or "").strip() and not _FENCE.search(md or ""):
        return _md_segment_html(md)
    return "\n".join(parts) if parts else ""


def _reading_css(pal: dict) -> tuple[str, str]:
    """成品文档纸面：颜色跟当前主题，不另做主题包。"""
    bg = _color(pal, "background", "#F5F5F7")
    paper = _color(pal, "surface", "#FFFFFF")
    ink = _color(pal, "text_primary", "#1D1D1F")
    muted = _color(pal, "text_secondary", "#3A3A3C")
    line = _color(pal, "border_default", "#D8D8DC")
    inset = _color(pal, "surface_inset", "#EBEBF0")
    link = _color(pal, "text_link", "#007AFF")
    mark = _color(pal, "warning_bg", "#FFF4E0")
    success = _color(pal, "success", "#34C759")
    success_bg = _color(pal, "success_bg", "#E8F8EC")
    warning = _color(pal, "warning", "#FF9F0A")
    warning_bg = _color(pal, "warning_bg", "#FFF4E0")
    info = _color(pal, "info", "#007AFF")
    info_bg = _color(pal, "info_bg", "#E5F1FF")
    dark = _luminance(bg) < 140
    mermaid_theme = "dark" if dark else "neutral"
    css = f"""
:root {{
  --bg: {bg};
  --paper: {paper};
  --ink: {ink};
  --muted: {muted};
  --line: {line};
  --inset: {inset};
  --link: {link};
  --mark: {mark};
  --success: {success};
  --success-bg: {success_bg};
  --warning: {warning};
  --warning-bg: {warning_bg};
  --info: {info};
  --info-bg: {info_bg};
}}
html, body {{
  margin: 0; padding: 0;
  background: var(--bg);
  color: var(--ink);
}}
body {{
  font-family: "Source Han Sans SC", "Microsoft YaHei UI", "PingFang SC", sans-serif;
  font-size: 17px;
  line-height: 1.8;
  -webkit-font-smoothing: antialiased;
}}
.sheet {{
  box-sizing: border-box;
  max-width: 720px;
  margin: 40px auto 80px;
  padding: 56px 64px 72px;
  background: var(--paper);
  color: var(--ink);
  border-radius: 4px;
  box-shadow: 0 1px 1px rgba(0,0,0,.04), 0 16px 48px rgba(0,0,0,.06);
}}
.md-body > *:first-child {{ margin-top: 0 !important; }}
.md-body h1, .md-body h1 span {{
  font-size: 2.05em !important;
  font-weight: 650 !important;
  letter-spacing: -0.025em;
  line-height: 1.22 !important;
  margin: 0 0 0.55em !important;
  font-family: "Source Han Sans SC", "Microsoft YaHei UI", "PingFang SC", sans-serif;
}}
.md-body h2, .md-body h2 span {{
  font-size: 1.42em !important;
  font-weight: 650 !important;
  line-height: 1.3 !important;
  margin: 1.55em 0 0.5em !important;
  padding-bottom: 0.22em;
  border-bottom: 1px solid var(--line);
  font-family: "Source Han Sans SC", "Microsoft YaHei UI", "PingFang SC", sans-serif;
}}
.md-body h3, .md-body h3 span {{
  font-size: 1.18em !important;
  font-weight: 650 !important;
  margin: 1.35em 0 0.4em !important;
}}
.md-body h4, .md-body h5, .md-body h6,
.md-body h4 span, .md-body h5 span, .md-body h6 span {{
  font-size: 1.02em !important;
  font-weight: 650 !important;
  margin: 1.15em 0 0.35em !important;
}}
.md-body strong, .md-body b {{ font-weight: 700; }}
.md-body em, .md-body i {{ font-style: italic; }}
.md-body s, .md-body del {{ text-decoration: line-through; }}
.md-body p {{ margin: 0 0 0.95em !important; }}
.md-body a {{ color: var(--link); text-decoration: none; }}
.md-body a:hover {{ text-decoration: underline; }}
.md-body ul, .md-body ol {{ margin: 0.2em 0 1.05em; padding-left: 1.4em; }}
.md-body li {{ margin: 0.28em 0; }}
.md-body li.task {{ list-style: none; margin-left: -0.15em; }}
.md-body li.task .box {{
  display: inline-block;
  width: 0.95em; height: 0.95em;
  margin-right: 0.45em;
  border: 1.5px solid var(--line);
  border-radius: 3px;
  vertical-align: -0.12em;
  background: transparent;
  box-sizing: border-box;
}}
.md-body li.task.done .box {{
  background: var(--link);
  border-color: var(--link);
  box-shadow: inset 0 0 0 2px var(--paper);
}}
.md-body blockquote {{
  margin: 1.05em 0 1.15em !important;
  padding: 0.1em 0 0.1em 1em;
  border-left: 3px solid var(--line);
  color: var(--muted);
  background: transparent;
}}
.md-body blockquote p {{ margin: 0.2em 0 !important; }}
.md-body blockquote.callout {{
  border-left-width: 4px;
  border-radius: 0 8px 8px 0;
  padding: 12px 16px 12px 14px;
  color: var(--ink);
}}
.md-body blockquote.callout .label {{
  font-family: "Microsoft YaHei UI", "PingFang SC", sans-serif;
  font-size: 0.78em;
  font-weight: 700;
  letter-spacing: 0.06em;
  margin-bottom: 0.25em;
}}
.md-body blockquote.callout.note {{
  border-color: var(--info);
  background: var(--info-bg);
}}
.md-body blockquote.callout.note .label {{ color: var(--info); }}
.md-body blockquote.callout.tip {{
  border-color: var(--success);
  background: var(--success-bg);
}}
.md-body blockquote.callout.tip .label {{ color: var(--success); }}
.md-body blockquote.callout.warning {{
  border-color: var(--warning);
  background: var(--warning-bg);
}}
.md-body blockquote.callout.warning .label {{ color: var(--warning); }}
.md-body hr {{
  border: 0; border-top: 1px solid var(--line);
  margin: 1.8em 0;
}}
.md-body pre {{
  background: var(--inset) !important;
  border-radius: 8px;
  padding: 14px 16px !important;
  margin: 0.4em 0 1.1em !important;
  overflow: auto;
  line-height: 1.55 !important;
}}
.md-body pre code {{
  font-family: "Cascadia Code", Consolas, "Sarasa Mono SC", monospace !important;
  font-size: 0.88em !important;
  background: transparent !important;
  padding: 0 !important;
}}
.md-body p code, .md-body li code {{
  font-family: "Cascadia Code", Consolas, "Sarasa Mono SC", monospace;
  font-size: 0.9em;
  background: var(--inset);
  padding: 0.08em 0.38em;
  border-radius: 4px;
}}
.md-body table {{
  width: 100%;
  border-collapse: collapse;
  margin: 0.4em 0 1.15em;
  font-size: 0.95em;
}}
.md-body th, .md-body td {{
  border: 1px solid var(--line) !important;
  padding: 8px 12px;
  text-align: left;
  vertical-align: top;
}}
.md-body th {{
  background: var(--inset);
  font-weight: 650;
}}
.md-body td p, .md-body th p {{ margin: 0 !important; }}
.md-body img {{
  max-width: 100% !important;
  height: auto !important;
  border-radius: 8px;
  margin: 0.6em 0 1em;
  box-shadow: 0 1px 2px rgba(0,0,0,.06);
}}
.md-body mark {{
  background: var(--mark) !important;
  color: inherit !important;
  padding: 0 0.18em;
  border-radius: 3px;
}}
.mermaid {{
  margin: 1.25em 0;
  padding: 8px 4px;
  text-align: center;
  overflow-x: auto;
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
}}
.empty {{ color: var(--muted); margin: 0; }}
"""
    return css, mermaid_theme


def build_reading_document_html(md: str) -> str:
    """只读阅读态：居中纸面，像打开一篇排好的文档。"""
    from modules.quick_notepad.md_text import prepare_markdown_for_preview

    prepared = prepare_markdown_for_preview(md or "")
    body_html = _md_without_mermaid_as_html(prepared)
    if not body_html.strip():
        body_html = '<p class="empty">这篇还是空的。</p>'
    css, mermaid_theme = _reading_css(_palette())
    js = ""
    if has_mermaid(prepared) and _MERMAID_JS.is_file():
        js_uri = QUrl.fromLocalFile(str(_MERMAID_JS.resolve())).toString()
        js = f"""
<script src="{js_uri}"></script>
<script>
mermaid.initialize({{ startOnLoad: true, theme: "{mermaid_theme}", securityLevel: "loose" }});
</script>
"""
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>{css}</style>
</head><body>
<article class="sheet"><div class="md-body">
{body_html}
</div></article>
{js}
</body></html>
"""


def build_mermaid_preview_html(md: str) -> str:
    """完整 HTML 文档：正文纸面 + 本机 mermaid。"""
    return build_reading_document_html(md)


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
