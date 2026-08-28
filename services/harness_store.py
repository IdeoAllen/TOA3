# -*- coding: utf-8 -*-
"""Harness 会话/用量只读存储（经 vendor/dshm 子进程 JSON）。"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from services.harness_config import dsh_home_path, dshm_script_path, load_harness_config, node_exe_path

logger = logging.getLogger(__name__)


def _run_dshm(args: list[str], *, timeout: float = 60.0) -> dict[str, Any] | list[Any] | None:
    node = node_exe_path()
    script = dshm_script_path()
    if not node.is_file() or not script.is_file():
        return None
    home = dsh_home_path()
    cmd = [str(node), str(script), "--home", str(home), "--json", *args]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if __import__("os").name == "nt" else 0,
        )
        if result.returncode != 0:
            logger.warning("dshm %s failed: %s", args[0], result.stderr.strip())
            return None
        raw = (result.stdout or "").strip()
        if not raw:
            return None
        return json.loads(raw)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
        logger.warning("dshm invoke error: %s", exc)
        return None


def status_snapshot() -> dict[str, Any]:
    data = _run_dshm(["status"])
    return data if isinstance(data, dict) else {}


def list_sessions(*, include_archived: bool = False) -> list[dict[str, Any]]:
    args = ["ls"]
    if include_archived:
        args.append("--all")
    data = _run_dshm(args)
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict) and isinstance(data.get("sessions"), list):
        return [x for x in data["sessions"] if isinstance(x, dict)]
    return []


def session_detail(session_id: str) -> dict[str, Any] | None:
    data = _run_dshm(["show", session_id])
    return data if isinstance(data, dict) else None


def search_sessions(query: str, *, limit: int = 30) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    data = _run_dshm(["search", q, "--limit", str(limit)])
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def trend_series(session_id: str) -> list[dict[str, Any]]:
    data = _run_dshm(["trend", session_id])
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def export_session_markdown(session_id: str, out_dir: Path) -> Path | None:
    """导出可读 Markdown 到指定目录。"""
    node = node_exe_path()
    script = dshm_script_path()
    if not node.is_file() or not script.is_file():
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    home = dsh_home_path()
    cmd = [
        str(node),
        str(script),
        "--home",
        str(home),
        "export",
        session_id,
        "--format",
        "md",
        "--out",
        str(out_dir),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            creationflags=subprocess.CREATE_NO_WINDOW if __import__("os").name == "nt" else 0,
        )
        if result.returncode != 0:
            return None
        # dshm 输出文件名基于 session id
        for p in out_dir.glob("*.md"):
            if session_id.replace("session-", "")[:8] in p.name or session_id in p.name:
                return p
        md_files = sorted(out_dir.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)
        return md_files[0] if md_files else None
    except (subprocess.TimeoutExpired, OSError):
        return None


def set_archived(session_id: str, archived: bool) -> bool:
    cmd = "archive" if archived else "unarchive"
    data = _run_dshm([cmd, session_id])
    return isinstance(data, dict) and data.get("ok")


def resume_info(session_id: str) -> dict[str, Any] | None:
    detail = session_detail(session_id)
    if detail:
        return detail
    data = _run_dshm(["resume", session_id])
    return data if isinstance(data, dict) else None


def list_workspaces() -> list[dict[str, Any]]:
    data = _run_dshm(["workspaces"])
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict) and isinstance(data.get("workspaces"), list):
        return [x for x in data["workspaces"] if isinstance(x, dict)]
    return []


def overview_from_status() -> dict[str, Any]:
    """合并 status 与 ls 为 UI 概览。"""
    snap = status_snapshot()
    sessions = list_sessions(include_archived=False)
    return {
        "status": snap,
        "sessions": sessions,
        "dsh_home": str(dsh_home_path()),
        "web_port": int(load_harness_config().get("web_port") or 3081),
    }
