# -*- coding: utf-8 -*-
"""OCR 最近一次结果暂存（services 层；截图链与 OCR 页共用）。"""
from __future__ import annotations

_last_text: str = ""
_last_path: str = ""


def stash_last_result(text: str, *, path: str = "") -> None:
    global _last_text, _last_path
    _last_text = text or ""
    _last_path = path or ""


def peek_last_result() -> tuple[str, str]:
    return _last_text, _last_path


def take_last_result() -> tuple[str, str]:
    global _last_text, _last_path
    text, path = _last_text, _last_path
    _last_text, _last_path = "", ""
    return text, path
