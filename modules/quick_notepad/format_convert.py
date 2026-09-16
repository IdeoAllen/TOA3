# -*- coding: utf-8 -*-
"""记事格式互转（TXT ↔ MD）。

安全约定（硬）：
1. TXT / MD 各有独立正文槽（bodies），切换优先恢复目标槽
2. 仅当目标槽为空时才做一次转换生成
3. 转换结果若为空而原文非空 → 拒绝覆盖
4. 遗留 HTML 槽只读：可单向抽出到 MD/TXT，UI 不再提供 HTML 格式
"""
from __future__ import annotations

from typing import Any

from PySide6.QtGui import QTextDocument

from modules.quick_notepad.rich_body import (
    is_full_html_document,
    is_qt_rich_html,
    is_toa_rich_html,
    strip_toa_html_marker,
)

_FMTS = ("txt", "md")


def _plain_from_html(html: str) -> str:
    doc = QTextDocument()
    doc.setHtml(strip_toa_html_marker(html or ""))
    return doc.toPlainText()


def _markdown_from_html(html: str) -> str:
    raw = strip_toa_html_marker(html or "")
    doc = QTextDocument()
    doc.setHtml(raw)
    try:
        out = doc.toMarkdown()
    except Exception:
        out = ""
    if (out or "").strip():
        return out
    return doc.toPlainText()


def convert_note_body(body: str, *, from_fmt: str, to_fmt: str) -> tuple[str, str]:
    """单次正文转换（不碰多槽）。返回 (new_body, hint)。"""
    src = str(from_fmt or "").strip().lower()
    dst = str(to_fmt or "").strip().lower()
    if dst not in _FMTS:
        dst = "md"
    if src not in _FMTS and src not in ("html", "htm", "web"):
        src = "md"
    raw = body or ""
    if src == dst:
        return raw, ""

    if dst == "txt":
        if src in ("html", "htm", "web") or is_toa_rich_html(raw) or is_qt_rich_html(raw):
            return _plain_from_html(raw), "已转为纯文本（样式不保留）"
        return raw, ""

    # dst == md
    if src == "txt":
        return raw, ""
    if src in ("html", "htm", "web") or is_toa_rich_html(raw) or is_qt_rich_html(raw):
        if is_full_html_document(raw) and not is_toa_rich_html(raw):
            return _plain_from_html(raw), "完整网页已抽出纯文本进 MD"
        return _markdown_from_html(raw), "已从 HTML 抽出 Markdown"
    return raw, ""


def switch_body_safe(
    *,
    current_body: str,
    from_fmt: str,
    to_fmt: str,
    bodies: dict[str, Any] | None,
) -> tuple[str, str, dict[str, str]]:
    """安全切换：写入来源槽 → 优先恢复目标槽 → 否则转换；绝不空覆盖。"""
    src = from_fmt if from_fmt in _FMTS else ("md" if from_fmt not in ("html",) else "md")
    # 若来源实际是遗留 html，仍按 html 转换逻辑
    raw_from = str(from_fmt or "").strip().lower()
    if raw_from in ("html", "htm", "web"):
        src_conv = "html"
        src_slot = "md"  # UI 不再写 html 槽
    else:
        src_conv = src
        src_slot = src if src in _FMTS else "md"
    dst = to_fmt if to_fmt in _FMTS else "md"
    cur = current_body if isinstance(current_body, str) else str(current_body or "")
    slot: dict[str, str] = {}
    if isinstance(bodies, dict):
        for k in ("txt", "md", "html"):
            if k in bodies and bodies[k] is not None:
                slot[k] = str(bodies[k])

    if cur.strip() or src_slot not in slot or not (slot.get(src_slot) or "").strip():
        slot[src_slot] = cur
    elif not cur.strip() and (slot.get(src_slot) or "").strip():
        cur = slot[src_slot]

    if src_slot == dst and src_conv != "html":
        return cur, "", slot

    existing = (slot.get(dst) or "").strip()
    if existing and src_conv != "html":
        return slot[dst], f"已恢复本记事的 {dst.upper()} 正文（未覆盖）", slot

    converted, hint = convert_note_body(cur, from_fmt=src_conv, to_fmt=dst)

    if cur.strip() and not (converted or "").strip():
        slot[dst] = cur
        return (
            cur,
            "转换结果为空，已保留原文到新格式（内容未丢）",
            slot,
        )

    slot[dst] = converted
    return converted, hint or f"已生成 {dst.upper()} 稿（原文已保留）", slot
