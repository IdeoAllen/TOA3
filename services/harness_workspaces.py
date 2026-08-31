# -*- coding: utf-8 -*-
"""Harness 工作区 / 本地项目文件夹。"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.harness_config import dsh_home_path, save_harness_config
from services.harness_store import list_workspaces

logger = logging.getLogger(__name__)


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


def ensure_workspace_registered(path: Path | str, *, title: str = "") -> str:
    """把目录登记进 DSH workspace.json（若已有同路径则前置到列表）。返回 workspace id。"""
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"工作区目录不存在：{root}")

    display = (title or root.name).strip() or root.name
    path_key = str(root)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    ws_path = _workspace_json_path()
    ws_path.parent.mkdir(parents=True, exist_ok=True)

    if ws_path.is_file():
        try:
            data = json.loads(ws_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
    else:
        data = {}

    if not isinstance(data, dict):
        data = {}
    data.setdefault("unit", {"name": "workspace", "version": 2})
    global_blk = data.setdefault("global", {})
    if not isinstance(global_blk, dict):
        global_blk = {}
        data["global"] = global_blk
    global_blk["initialized"] = True
    ids: list[str] = list(global_blk.get("workspaceIds") or [])
    tables = data.setdefault("tables", {})
    if not isinstance(tables, dict):
        tables = {}
        data["tables"] = tables
    ws_table = tables.setdefault("workspaces", {})
    if not isinstance(ws_table, dict):
        ws_table = {}
        tables["workspaces"] = ws_table

    existing_id = ""
    for wid, row in ws_table.items():
        if not isinstance(row, dict):
            continue
        try:
            if Path(str(row.get("path") or "")).resolve() == root:
                existing_id = str(wid)
                break
        except OSError:
            continue

    if existing_id:
        wid = existing_id
        row = ws_table[wid]
        if isinstance(row, dict):
            row["title"] = display
            row["path"] = path_key
            row["updatedAt"] = now
        ids = [wid] + [x for x in ids if x != wid]
    else:
        wid = str(uuid.uuid4())
        ws_table[wid] = {
            "path": path_key,
            "title": display,
            "sessionIds": [],
            "createdAt": now,
            "updatedAt": now,
        }
        ids = [wid] + [x for x in ids if x != wid]

    global_blk["workspaceIds"] = ids
    ws_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    set_default_workspace_path(path_key)
    logger.info("Harness workspace registered: %s → %s", display, path_key)
    return wid


def unregister_workspace_by_path(path: Path | str) -> int:
    """从 workspace.json 移除指向该路径的工作区条目。返回删除条数。"""
    root = Path(path).expanduser().resolve()
    ws_path = _workspace_json_path()
    if not ws_path.is_file():
        return 0
    try:
        data = json.loads(ws_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0
    tables = data.get("tables") or {}
    wstab = tables.get("workspaces") or {}
    if not isinstance(wstab, dict):
        return 0
    drop: list[str] = []
    for wid, row in wstab.items():
        if not isinstance(row, dict):
            continue
        try:
            if Path(str(row.get("path") or "")).resolve() == root:
                drop.append(str(wid))
        except OSError:
            continue
    if not drop:
        return 0
    for wid in drop:
        wstab.pop(wid, None)
    global_blk = data.setdefault("global", {})
    ids = [i for i in list(global_blk.get("workspaceIds") or []) if i not in drop]
    global_blk["workspaceIds"] = ids
    ws_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return len(drop)


def open_extension_dev_session(
    shell,
    root: Path | str,
    *,
    name: str = "",
    description: str = "",
    plugin_id: str = "",
) -> None:
    """兼容入口：委托生命周期 start_development。"""
    from services.extension_lifecycle import start_development

    start_development(
        shell,
        plugin_id=plugin_id,
        root=root,
        name=name,
        description=description,
    )
