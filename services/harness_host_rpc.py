# -*- coding: utf-8 -*-
"""
DeepSeek Harness Host 一元 RPC（浏览器同源协议）。

写 workspace.json 不会刷新「外部实例」内存；必须走：
  POST /api/<method>  body={type,rpcId,method,payload}
才能让侧栏立刻出现工作区/会话，并用 session.prompt 真正投喂。
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _base_url() -> str:
    from services.harness_config import web_url

    return str(web_url() or "http://127.0.0.1:3081").rstrip("/")


def host_rpc(method: str, payload: dict[str, Any] | None = None, *, timeout: float = 15.0) -> dict[str, Any]:
    """
    调用 Host 一元 RPC。成功返回 result.value；失败抛 ValueError（含 code/message）。
    服务未开时抛 ConnectionError。
    """
    name = str(method or "").strip()
    if not name:
        raise ValueError("RPC method 为空")
    body = {
        "type": "client-request",
        "rpcId": str(uuid.uuid4()),
        "method": name,
        "payload": payload if isinstance(payload, dict) else {},
    }
    url = f"{_base_url()}/api/{name}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "content-type": "application/json",
            "accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except Exception:
            detail = str(exc)
        raise ConnectionError(f"Harness RPC HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ConnectionError(f"Harness 服务不可达：{exc}") from exc

    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Harness RPC 返回非 JSON：{raw[:200]}") from exc

    result = envelope.get("result") if isinstance(envelope, dict) else None
    if not isinstance(result, dict):
        raise ValueError(f"Harness RPC 无 result：{raw[:200]}")
    if result.get("ok") is True:
        value = result.get("value")
        return value if isinstance(value, dict) else {"value": value}
    err = result.get("error") if isinstance(result.get("error"), dict) else {}
    code = str(err.get("code") or "error")
    msg = str(err.get("message") or raw[:200])
    raise ValueError(f"{code}: {msg}")


def host_reachable(*, timeout: float = 2.0) -> bool:
    try:
        host_rpc("workspace.list", {}, timeout=timeout)
        return True
    except Exception:
        return False


def list_workspaces_live() -> list[dict[str, Any]]:
    value = host_rpc("workspace.list", {})
    items = value.get("items")
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict)]


def find_workspace_by_path(path: Path | str) -> dict[str, Any] | None:
    root = Path(path).expanduser().resolve()
    for row in list_workspaces_live():
        try:
            if Path(str(row.get("path") or "")).resolve() == root:
                return row
        except OSError:
            continue
    return None


def ensure_workspace_live(path: Path | str, *, title: str = "") -> dict[str, Any]:
    """
    经 Host API 登记工作区（侧栏立即可见）。目录必须已存在。
    返回 workspace 视图 dict（含 workspaceId / path / title / sessionIds）。
    """
    root = Path(path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"工作区目录不存在：{root}")
    display = (title or root.name).strip() or root.name

    existing = find_workspace_by_path(root)
    if existing:
        wid = str(existing.get("workspaceId") or "")
        if display and str(existing.get("title") or "") != display and wid:
            try:
                value = host_rpc(
                    "workspace.rename",
                    {"workspaceId": wid, "title": display},
                )
                ws = value.get("workspace")
                if isinstance(ws, dict):
                    return ws
            except ValueError as exc:
                logger.warning("workspace.rename failed: %s", exc)
        return existing

    value = host_rpc("workspace.create", {"path": str(root)})
    ws = value.get("workspace")
    if not isinstance(ws, dict):
        raise ValueError("workspace.create 未返回 workspace")
    wid = str(ws.get("workspaceId") or "")
    if display and str(ws.get("title") or "") != display and wid:
        try:
            renamed = host_rpc(
                "workspace.rename",
                {"workspaceId": wid, "title": display},
            )
            rws = renamed.get("workspace")
            if isinstance(rws, dict):
                return rws
        except ValueError as exc:
            logger.warning("workspace.rename after create failed: %s", exc)
    return ws


def create_session_live(
    workspace_id: str,
    *,
    title: str = "",
) -> dict[str, Any]:
    """在指定工作区新建会话；可选改标题。返回 {sessionId, ...}。"""
    wid = str(workspace_id or "").strip()
    if not wid:
        raise ValueError("workspaceId 为空")
    value = host_rpc("session.create", {"workspaceId": wid})
    sid = str(value.get("sessionId") or "").strip()
    if not sid:
        raise ValueError("session.create 未返回 sessionId")
    display = (title or "").strip()
    if display:
        try:
            host_rpc("session.rename", {"sessionId": sid, "title": display})
            value["title"] = display
        except ValueError as exc:
            logger.warning("session.rename failed: %s", exc)
    return value


def cancel_session_live(session_id: str) -> bool:
    """中断当前回合（session.cancel）。"""
    sid = str(session_id or "").strip()
    if not sid:
        return False
    value = host_rpc("session.cancel", {"sessionId": sid})
    return bool(value.get("accepted"))


def execute_slash_command_live(session_id: str, line: str) -> dict[str, Any]:
    """
    执行会话斜杠命令（Typert commands/execute）。
    例：/permission workspace-write
    """
    sid = str(session_id or "").strip()
    body = str(line or "").strip()
    if not sid or not body:
        raise ValueError("sessionId / line 为空")
    return host_rpc(
        "commands/execute",
        {"args": {"agentId": sid, "line": body}},
    )


def pin_workspace_write_live(session_id: str) -> bool:
    """把会话沙箱钉在 workspace-write（只锁写；读仍靠 TOA 围栏）。"""
    try:
        execute_slash_command_live(session_id, "/permission workspace-write")
        return True
    except Exception as exc:
        logger.warning("pin workspace-write failed: %s", exc)
        return False


def prompt_session_live(
    session_id: str,
    text: str,
    *,
    mode: str = "queue",
) -> bool:
    """把文本投进会话队列（真正投喂，无需点发送）。"""
    sid = str(session_id or "").strip()
    body = (text or "").strip()
    if not sid or not body:
        return False
    m = mode if mode in ("queue", "steer") else "queue"
    value = host_rpc(
        "session.prompt",
        {
            "sessionId": sid,
            "mode": m,
            "content": [{"type": "text", "text": body}],
        },
    )
    return bool(value.get("accepted"))
