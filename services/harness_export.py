# -*- coding: utf-8 -*-
"""导出 Harness 会话 Markdown（TOA output 可追溯）。"""
from __future__ import annotations

from pathlib import Path

from services.harness_store import export_session_markdown, list_sessions


def export_most_recent_session(out_dir: Path) -> tuple[Path | None, str]:
    """取最近一条未归档会话导出；返回 (路径, 会话标题)。"""
    sessions = list_sessions(include_archived=False)
    if not sessions:
        return None, ""
    # dshm ls 通常已按时间；取第一条
    pick = sessions[0]
    sid = str(pick.get("id") or "").strip()
    if not sid:
        return None, ""
    title = str(pick.get("title") or "未命名")
    path = export_session_markdown(sid, out_dir)
    return path, title
