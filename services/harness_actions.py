# -*- coding: utf-8 -*-
"""Harness 快捷动作（命令面板 / 壳层复用）。"""
from __future__ import annotations

from core.status_service import StatusLevel
from core.user_messages import show_info, show_warning


def palette_actions() -> list[tuple[str, str, str]]:
    """(action_id, 展示名, 搜索关键词补充)。"""
    return [
        ("harness:start", "启动 Harness Sidecar", "harness 启动 sidecar dsh"),
        ("harness:open", "打开编码智能体页", "harness 智能体 codex agent"),
    ]


def run_palette_action(shell, action_id: str) -> bool:
    """执行命令面板快捷动作。"""
    aid = str(action_id or "").strip()
    if aid == "harness:start":
        from services.harness_sidecar import start

        ok, msg = start()
        if ok:
            show_info(shell, msg)
            if hasattr(shell, "show_status"):
                shell.show_status(msg, level=StatusLevel.SUCCESS)
        else:
            show_warning(shell, msg)
        return True
    if aid == "harness:open":
        if hasattr(shell, "_summon_module"):
            shell._summon_module("harness_agent")
        elif hasattr(shell, "navigate"):
            shell.navigate("harness_agent")
        return True
    return False
