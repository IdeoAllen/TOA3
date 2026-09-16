# -*- coding: utf-8 -*-
"""Markdown 正文小工具：净化源码、预览前展开 ==高亮==。"""
from __future__ import annotations

import html as html_lib
import re

_TAG_RE = re.compile(r"<[^>]+>")
_MD_HIGHLIGHT_EQ = re.compile(r"==([^=\n]+)==")
_LEGACY_HL_SPAN = re.compile(
    r'<span\s+style="[^"]*background-color\s*:\s*#(?:FEF08A|fef08a|FF0|ffff00)[^"]*"[^>]*>(.*?)</span>',
    re.I | re.DOTALL,
)
_LEGACY_HL_MARK = re.compile(r"<mark\b[^>]*>(.*?)</mark>", re.I | re.DOTALL)
# 保护代码围栏 / 行内代码，避免误伤手写 MD
_FENCE = re.compile(r"(```[\s\S]*?```|~~~[\s\S]*?~~~)")
_INLINE_CODE = re.compile(r"`[^`\n]+`")


def sanitize_md_source(text: str) -> str:
    """编辑区纯 Markdown：把误插入的高亮 HTML 收成 ==…==。"""
    raw = text or ""

    def _to_eq(m: re.Match[str]) -> str:
        inner = html_lib.unescape(_TAG_RE.sub("", m.group(1) or "")).strip()
        return f"=={inner or '高亮'}=="

    raw = _LEGACY_HL_SPAN.sub(_to_eq, raw)
    raw = _LEGACY_HL_MARK.sub(_to_eq, raw)
    return raw


def _expand_highlight_outside_code(text: str) -> str:
    """只在代码外把 ==高亮== 收成 <mark>，供 setMarkdown。"""
    raw = text or ""
    slots: list[str] = []

    def _park(m: re.Match[str]) -> str:
        slots.append(m.group(0))
        return f"\x00MDCODE{len(slots) - 1}\x00"

    raw = _FENCE.sub(_park, raw)
    raw = _INLINE_CODE.sub(_park, raw)
    raw = _MD_HIGHLIGHT_EQ.sub(
        r'<mark style="background-color:#FEF08A;color:#334155;">\1</mark>',
        raw,
    )
    for i, piece in enumerate(slots):
        raw = raw.replace(f"\x00MDCODE{i}\x00", piece)
    return raw


def expand_md_highlight(text: str) -> str:
    """sanitize 后展开高亮（代码区不碰）。"""
    return _expand_highlight_outside_code(sanitize_md_source(text or ""))


def prepare_markdown_for_preview(text: str) -> str:
    """手写 / 组件同源：预览前唯一准备入口。"""
    return expand_md_highlight(text or "")
