# -*- coding: utf-8 -*-
"""扣分备注整理：Excel 粘贴 → 带序号、去空白行的规范文本。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_SPLIT_RE = re.compile(r"[\n\r；;]+")
_QUOTE_WRAP_RE = re.compile(r'^[\s"""「」『』]+|[\s"""「」『』]+$')
_LEADING_INDEX_RE = re.compile(
    r"^(?:"
    r"\d{1,3}\s*[.．、．]\s*"
    r"|\d{1,3}\s*[)）]\s*"
    r"|[（(]\s*\d{1,3}\s*[)）]\s*"
    r"|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳]\s*"
    r")"
)

POINTS_PER_ITEM = 5
FULL_SCORE = 100


@dataclass
class FormatResult:
    lines: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @property
    def count(self) -> int:
        return len(self.lines)


def score_from_item_count(
    n: int, *, full: int = FULL_SCORE, per: int = POINTS_PER_ITEM
) -> tuple[int, int]:
    n = max(0, int(n or 0))
    deducted = per * n
    return full - deducted, deducted


def strip_leading_index(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    for _ in range(2):
        nxt = _LEADING_INDEX_RE.sub("", t, count=1).strip()
        if nxt == t:
            break
        t = nxt
    return t


def split_clauses(raw: str) -> list[str]:
    parts: list[str] = []
    for chunk in _SPLIT_RE.split(raw or ""):
        t = (chunk or "").strip()
        if not t:
            continue
        t = _QUOTE_WRAP_RE.sub("", t).strip()
        if not t:
            continue
        t = re.sub(r"[ \t]+", " ", t)
        t = strip_leading_index(t)
        if t:
            parts.append(t)
    return parts


def format_deduction_notes(raw: str) -> FormatResult:
    clauses = split_clauses(raw)
    lines = [f"{i}、{text}" for i, text in enumerate(clauses, 1)]
    return FormatResult(lines=lines)


def format_lines(raw: str) -> str:
    return format_deduction_notes(raw).text
