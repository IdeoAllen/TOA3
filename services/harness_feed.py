# -*- coding: utf-8 -*-
"""办公链 → Harness 智能体投喂。"""
from __future__ import annotations

from PySide6.QtGui import QGuiApplication


_INCOMING: dict[str, str] = {"text": "", "title": "", "source": ""}


def stash_feed(text: str, *, title: str = "", source: str = "") -> None:
    _INCOMING["text"] = (text or "").strip()
    _INCOMING["title"] = (title or "").strip()
    _INCOMING["source"] = (source or "").strip()


def pop_feed() -> dict[str, str]:
    out = dict(_INCOMING)
    _INCOMING["text"] = ""
    _INCOMING["title"] = ""
    _INCOMING["source"] = ""
    return out


def peek_feed() -> dict[str, str]:
    return dict(_INCOMING)


def format_feed_message(feed: dict[str, str]) -> str:
    text = str(feed.get("text") or "").strip()
    if not text:
        return ""
    title = str(feed.get("title") or "").strip()
    source = str(feed.get("source") or "").strip()
    head_parts = []
    if source:
        head_parts.append(f"来源：{source}")
    if title:
        head_parts.append(title)
    head = " · ".join(head_parts)
    if head:
        return f"【{head}】\n\n{text}\n\n---\n请基于以上内容继续处理。"
    return text


def copy_to_clipboard(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    clip = QGuiApplication.clipboard()
    if clip is None:
        return False
    clip.setText(t)
    return True


def navigate_to_harness(shell, text: str, *, title: str = "", source: str = "") -> None:
    stash_feed(text, title=title, source=source)
    if hasattr(shell, "navigate"):
        shell.navigate("harness_agent")
    elif hasattr(shell, "_summon_module"):
        shell._summon_module("harness_agent")
