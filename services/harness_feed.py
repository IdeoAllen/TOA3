# -*- coding: utf-8 -*-
"""办公链 → Harness 智能体投喂。"""
from __future__ import annotations

from PySide6.QtGui import QGuiApplication


_INCOMING: dict[str, str] = {
    "text": "",
    "title": "",
    "source": "",
    "workspace_title": "",
    "workspace_path": "",
    "auto_prepare": "",
    "need_reload": "",
    "plugin_id": "",
    "session_id": "",
    "already_prompted": "",
    "session_title": "",
}


def stash_feed(
    text: str,
    *,
    title: str = "",
    source: str = "",
    workspace_title: str = "",
    workspace_path: str = "",
    auto_prepare: bool = False,
    need_reload: bool = False,
    plugin_id: str = "",
    session_id: str = "",
    already_prompted: bool = False,
    session_title: str = "",
) -> None:
    _INCOMING["text"] = (text or "").strip()
    _INCOMING["title"] = (title or "").strip()
    _INCOMING["source"] = (source or "").strip()
    _INCOMING["workspace_title"] = (workspace_title or "").strip()
    _INCOMING["workspace_path"] = (workspace_path or "").strip()
    _INCOMING["auto_prepare"] = "1" if auto_prepare else ""
    _INCOMING["need_reload"] = "1" if need_reload else ""
    _INCOMING["plugin_id"] = (plugin_id or "").strip()
    _INCOMING["session_id"] = (session_id or "").strip()
    _INCOMING["already_prompted"] = "1" if already_prompted else ""
    _INCOMING["session_title"] = (session_title or "").strip()


def pop_feed() -> dict[str, str]:
    out = dict(_INCOMING)
    for k in _INCOMING:
        _INCOMING[k] = ""
    return out


def peek_feed() -> dict[str, str]:
    return dict(_INCOMING)


def format_feed_message(feed: dict[str, str]) -> str:
    text = str(feed.get("text") or "").strip()
    if not text:
        return ""
    title = str(feed.get("title") or "").strip()
    source = str(feed.get("source") or "").strip()
    if source.startswith("系统设置") or title.startswith("开发扩展"):
        return text
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


def navigate_to_harness(
    shell,
    text: str,
    *,
    title: str = "",
    source: str = "",
    workspace_title: str = "",
    workspace_path: str = "",
    auto_prepare: bool = False,
    need_reload: bool = False,
    plugin_id: str = "",
    session_id: str = "",
    already_prompted: bool = False,
    session_title: str = "",
) -> None:
    stash_feed(
        text,
        title=title,
        source=source,
        workspace_title=workspace_title,
        workspace_path=workspace_path,
        auto_prepare=auto_prepare,
        need_reload=need_reload,
        plugin_id=plugin_id,
        session_id=session_id,
        already_prompted=already_prompted,
        session_title=session_title,
    )
    if hasattr(shell, "navigate"):
        shell.navigate("harness_agent")
    elif hasattr(shell, "_summon_module"):
        shell._summon_module("harness_agent")
