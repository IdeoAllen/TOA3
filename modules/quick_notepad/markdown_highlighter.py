# -*- coding: utf-8 -*-
"""Markdown 语法高亮（记事「多功能」模式）。"""
from __future__ import annotations

import re

from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat


def _fmt(
    *,
    color: str | None = None,
    bold: bool = False,
    italic: bool = False,
    mono: bool = False,
) -> QTextCharFormat:
    f = QTextCharFormat()
    if color:
        f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Weight.Bold)
    if italic:
        f.setFontItalic(True)
    if mono:
        f.setFontFamilies(["Cascadia Code", "Consolas", "Courier New", "monospace"])
    return f


class MarkdownHighlighter(QSyntaxHighlighter):
    """常见 Markdown：标题 / 强调 / 代码 / 链接 / 列表 / 引用 / 分割线。"""

    def __init__(self, document, palette: dict | None = None) -> None:
        super().__init__(document)
        self.set_palette(palette or {})

    def set_palette(self, palette: dict) -> None:
        p = palette or {}
        text = str(p.get("text_primary") or p.get("text") or "#1F2937")
        muted = str(p.get("text_secondary") or p.get("text_muted") or "#6B7280")
        primary = str(p.get("primary") or "#2563EB")
        success = str(p.get("success") or "#059669")
        warning = str(p.get("warning") or "#D97706")
        danger = str(p.get("danger") or "#DC2626")

        self._heading = _fmt(color=primary, bold=True)
        self._bold = _fmt(color=text, bold=True)
        self._italic = _fmt(color=text, italic=True)
        self._strike = _fmt(color=muted)
        self._strike.setFontStrikeOut(True)
        self._code = _fmt(color=danger, mono=True)
        self._code_block = _fmt(color=success, mono=True)
        self._link = _fmt(color=primary)
        self._quote = _fmt(color=muted, italic=True)
        self._list = _fmt(color=warning, bold=True)
        self._hr = _fmt(color=muted)
        self._html = _fmt(color=muted, mono=True)
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        if text.startswith("```") or text.startswith("~~~"):
            self.setFormat(0, len(text), self._code_block)
            return
        if re.match(r"^#{1,6}\s", text):
            self.setFormat(0, len(text), self._heading)
            return
        if re.match(r"^(\s{0,3})([-*_]){3,}\s*$", text):
            self.setFormat(0, len(text), self._hr)
            return
        if re.match(r"^\s{0,3}>\s?", text):
            self.setFormat(0, len(text), self._quote)
            return
        m = re.match(r"^(\s*)([-*+]|\d+\.)\s+", text)
        if m:
            self.setFormat(0, m.end(), self._list)
        m = re.match(r"^(\s*)-\s\[[ xX]\]\s+", text)
        if m:
            self.setFormat(0, m.end(), self._list)

        for rx, fmt in (
            (r"`[^`\n]+`", self._code),
            (r"\*\*[^*\n]+\*\*", self._bold),
            (r"__[^_\n]+__", self._bold),
            (r"(?<!\*)\*[^*\n]+\*(?!\*)", self._italic),
            (r"(?<!_)_[^_\n]+_(?!_)", self._italic),
            (r"~~[^~\n]+~~", self._strike),
            (r"!\[[^\]]*\]\([^)]+\)", self._link),
            (r"(?<!!)\[[^\]]*\]\([^)]+\)", self._link),
            (r"<https?://[^>\s]+>", self._link),
            (r"</?[a-zA-Z][^>]*>", self._html),
        ):
            for m in re.finditer(rx, text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)
