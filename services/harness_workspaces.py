# -*- coding: utf-8 -*-
"""Harness 工作区 / 本地项目文件夹。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from services.harness_config import dsh_home_path, save_harness_config
from services.harness_store import list_workspaces


def _workspace_json_path() -> Path:
    return dsh_home_path() / "storages" / "workspace.json"


def list_workspaces_from_store() -> list[dict[str, Any]]:
    items = list_workspaces()
    if items:
        return items
    path = _workspace_json_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        tables = data.get("tables") or {}
        ws_table = tables.get("workspaces") or {}
        out: list[dict[str, Any]] = []
        for wid, row in ws_table.items():
            if not isinstance(row, dict):
                continue
            out.append(
                {
                    "id": wid,
                    "title": row.get("title") or row.get("path") or wid,
                    "path": row.get("path") or "",
                    "sessionCount": len(row.get("sessionIds") or []),
                }
            )
        return out
    except (json.JSONDecodeError, OSError):
        return []


def set_default_workspace_path(path: str) -> None:
    save_harness_config({"default_workspace": (path or "").strip()})


def get_default_workspace_path() -> str:
    from services.harness_config import load_harness_config

    return str(load_harness_config().get("default_workspace") or "").strip()
