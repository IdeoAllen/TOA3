# -*- coding: utf-8 -*-
"""快速记事本存储：大纲树（每条记事均可作父节点；Tab 降级 / Shift+Tab 升级）。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from services.storage_paths import module_data_dir

_STORE: list[dict[str, Any]] | None = None
_SCHEMA_VERSION = 3


def _path() -> Path:
    return module_data_dir("quick_notepad", create=True) / "notes.json"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _normalize_node(raw: dict[str, Any]) -> dict[str, Any] | None:
    """统一为记事节点；旧 folder 迁移为可含子项的记事。"""
    kind = str(raw.get("kind") or raw.get("type") or "note").strip().lower()
    title = str(raw.get("title") or ("新目录" if kind == "folder" else "无标题")).strip()
    nid = str(raw.get("id") or uuid.uuid4().hex[:12])
    parent = raw.get("parent_id")
    parent_id = None if parent in (None, "", "null") else str(parent)
    order = int(raw.get("order") or 0)
    body = str(raw.get("body") or "")
    updated = str(raw.get("updated") or _now())
    return {
        "id": nid,
        "kind": "note",
        "title": title,
        "body": body,
        "parent_id": parent_id,
        "order": order,
        "updated": updated,
    }


def _migrate_v1_list(raw: list[Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        node = _normalize_node(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "body": item.get("body"),
                "parent_id": None,
                "order": i,
                "updated": item.get("updated"),
            }
        )
        if node:
            nodes.append(node)
    return nodes


def load_nodes() -> list[dict[str, Any]]:
    global _STORE
    if _STORE is not None:
        return _STORE
    path = _path()
    if not path.is_file():
        _STORE = []
        return _STORE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("nodes"), list):
            nodes = [_normalize_node(x) for x in raw["nodes"] if isinstance(x, dict)]
            _STORE = [n for n in nodes if n]
            ver = int(raw.get("schema_version") or 0)
            if ver < _SCHEMA_VERSION:
                save_nodes(_STORE)
            return _STORE
        if isinstance(raw, list):
            _STORE = _migrate_v1_list(raw)
            save_nodes(_STORE)
            return _STORE
    except Exception:
        pass
    _STORE = []
    return _STORE


def save_nodes(nodes: list[dict[str, Any]]) -> None:
    global _STORE
    cleaned = [_normalize_node(n) for n in nodes if isinstance(n, dict)]
    _STORE = [n for n in cleaned if n]
    payload = {"schema_version": _SCHEMA_VERSION, "nodes": _STORE}
    _path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def invalidate_cache() -> None:
    global _STORE
    _STORE = None


def load_notes() -> list[dict[str, Any]]:
    return list(load_nodes())


def save_notes(notes: list[dict[str, Any]]) -> None:
    save_nodes(notes)


def find_node(node_id: str) -> dict[str, Any] | None:
    sid = str(node_id or "").strip()
    for n in load_nodes():
        if str(n.get("id")) == sid:
            return n
    return None


def find_note(note_id: str) -> dict[str, Any] | None:
    return find_node(note_id)


def children_of(parent_id: str | None) -> list[dict[str, Any]]:
    pid = None if parent_id in (None, "") else str(parent_id)
    out = [n for n in load_nodes() if (n.get("parent_id") or None) == pid]
    out.sort(key=lambda x: (int(x.get("order") or 0), str(x.get("title") or "")))
    return out


def _next_order(parent_id: str | None) -> int:
    sibs = children_of(parent_id)
    if not sibs:
        return 0
    return max(int(x.get("order") or 0) for x in sibs) + 1


def _reindex_siblings(parent_id: str | None) -> None:
    sibs = children_of(parent_id)
    for i, n in enumerate(sibs):
        n["order"] = i


def _is_descendant(ancestor_id: str, maybe_child_id: str) -> bool:
    """maybe_child 是否在 ancestor 子树内（含自身）。"""
    cur = find_node(maybe_child_id)
    seen: set[str] = set()
    while cur is not None:
        cid = str(cur.get("id"))
        if cid == str(ancestor_id):
            return True
        if cid in seen:
            break
        seen.add(cid)
        pid = cur.get("parent_id")
        if not pid:
            return False
        cur = find_node(str(pid))
    return False


def add_note(title: str, body: str, *, parent_id: str | None = None) -> dict[str, Any]:
    nodes = load_nodes()
    entry = _normalize_node(
        {
            "id": uuid.uuid4().hex[:12],
            "title": (title or "新记事").strip(),
            "body": body or "",
            "parent_id": parent_id,
            "order": _next_order(parent_id),
            "updated": _now(),
        }
    )
    if entry is None:
        raise ValueError("invalid note")
    nodes.append(entry)
    save_nodes(nodes)
    return entry


def update_note(note_id: str, title: str, body: str) -> bool:
    nodes = load_nodes()
    for n in nodes:
        if str(n.get("id")) == note_id:
            n["title"] = (title or "无标题").strip()
            n["body"] = body or ""
            n["updated"] = _now()
            save_nodes(nodes)
            return True
    return False


def update_node_title(node_id: str, title: str) -> bool:
    nodes = load_nodes()
    for n in nodes:
        if str(n.get("id")) == node_id:
            n["title"] = (title or n.get("title") or "").strip()
            n["updated"] = _now()
            save_nodes(nodes)
            return True
    return False


def delete_node(node_id: str) -> bool:
    """删除节点；子节点提升到原父级下。"""
    sid = str(node_id or "").strip()
    nodes = load_nodes()
    target = next((n for n in nodes if str(n.get("id")) == sid), None)
    if target is None:
        return False
    parent_id = target.get("parent_id")
    pid = None if parent_id in (None, "") else str(parent_id)
    for n in nodes:
        if str(n.get("parent_id") or "") == sid:
            n["parent_id"] = pid
    kept = [n for n in nodes if str(n.get("id")) != sid]
    save_nodes(kept)
    _reindex_siblings(pid)
    save_nodes(load_nodes())
    return True


def delete_note(note_id: str) -> bool:
    return delete_node(note_id)


def apply_tree_layout(rows: list[tuple[str, str | None, int]]) -> None:
    """批量更新 parent_id / order（拖拽结束后）。"""
    nodes = load_nodes()
    by_id = {str(n.get("id")): n for n in nodes}
    seen: set[str] = set()
    for nid, parent_id, order in rows:
        n = by_id.get(str(nid))
        if n is None:
            continue
        pid = None if parent_id in (None, "") else str(parent_id)
        if pid and (pid == str(nid) or _is_descendant(str(nid), pid)):
            pid = None
        if pid and pid not in by_id:
            pid = None
        n["parent_id"] = pid
        n["order"] = int(order)
        seen.add(str(nid))
    # 未出现在树中的节点保持原 parent，但修复悬空父引用
    for nid, n in by_id.items():
        if nid in seen:
            continue
        pid = n.get("parent_id")
        if pid and str(pid) not in by_id:
            n["parent_id"] = None
    save_nodes(list(by_id.values()))
    sanitize_tree()


def move_node(node_id: str, new_parent_id: str | None, order: int) -> bool:
    """把节点挂到新父级下的指定顺序（子树跟随）。"""
    node = find_node(node_id)
    if node is None:
        return False
    new_pid = None if new_parent_id in (None, "") else str(new_parent_id)
    if new_pid == str(node_id) or (new_pid and _is_descendant(str(node_id), new_pid)):
        return False
    if new_pid and find_node(new_pid) is None:
        return False
    old_parent = node.get("parent_id")
    old_pid = None if old_parent in (None, "") else str(old_parent)
    node["parent_id"] = new_pid
    sibs = [s for s in children_of(new_pid) if str(s.get("id")) != str(node_id)]
    order = max(0, min(int(order), len(sibs)))
    sibs.insert(order, node)
    for i, s in enumerate(sibs):
        s["order"] = i
    save_nodes(load_nodes())
    if old_pid != new_pid:
        _reindex_siblings(old_pid)
        save_nodes(load_nodes())
    sanitize_tree()
    return True


def sanitize_tree() -> None:
    """修复悬空父级、环与兄弟 order，避免节点「消失」。"""
    nodes = load_nodes()
    by_id = {str(n.get("id")): n for n in nodes}
    for n in nodes:
        pid = n.get("parent_id")
        if not pid:
            n["parent_id"] = None
            continue
        pid_s = str(pid)
        if pid_s not in by_id or pid_s == str(n.get("id")) or _is_descendant(str(n.get("id")), pid_s):
            n["parent_id"] = None
    save_nodes(nodes)
    parents: set[str | None] = {None}
    for n in load_nodes():
        parents.add(None if not n.get("parent_id") else str(n.get("parent_id")))
    for pid in parents:
        _reindex_siblings(pid)
    save_nodes(load_nodes())


def indent_node(node_id: str) -> bool:
    """Tab：降级 —— 成为上一同级兄弟的最后一个子节点。"""
    node = find_node(node_id)
    if node is None:
        return False
    parent_id = node.get("parent_id")
    pid = None if parent_id in (None, "") else str(parent_id)
    sibs = children_of(pid)
    idx = next((i for i, s in enumerate(sibs) if str(s.get("id")) == str(node_id)), -1)
    if idx <= 0:
        return False
    prev_id = str(sibs[idx - 1].get("id"))
    new_order = _next_order(prev_id)
    node["parent_id"] = prev_id
    node["order"] = new_order
    save_nodes(load_nodes())
    _reindex_siblings(pid)
    save_nodes(load_nodes())
    sanitize_tree()
    return True


def outdent_node(node_id: str) -> bool:
    """Shift+Tab：升级 —— 提到父节点之后、与父同级。"""
    node = find_node(node_id)
    if node is None:
        return False
    parent_id = node.get("parent_id")
    if not parent_id:
        return False
    parent = find_node(str(parent_id))
    if parent is None:
        return False
    grand = parent.get("parent_id")
    grand_id = None if grand in (None, "") else str(grand)
    old_parent = str(parent_id)

    # 祖父级兄弟顺序：… 父 → 本节点 → …
    grand_sibs = [s for s in children_of(grand_id) if str(s.get("id")) != str(node_id)]
    insert_at = next(
        (i for i, s in enumerate(grand_sibs) if str(s.get("id")) == old_parent),
        -1,
    )
    insert_at = insert_at + 1 if insert_at >= 0 else len(grand_sibs)
    node["parent_id"] = grand_id
    grand_sibs.insert(insert_at, node)
    for i, s in enumerate(grand_sibs):
        s["order"] = i
    save_nodes(load_nodes())
    _reindex_siblings(old_parent)
    save_nodes(load_nodes())
    sanitize_tree()
    return True


def insert_note_after(after_id: str | None, *, title: str = "新记事", body: str = "") -> dict[str, Any]:
    """Outline 风格：在指定条目后新建同级记事。"""
    if not after_id:
        return add_note(title, body, parent_id=None)
    anchor = find_node(after_id)
    if anchor is None:
        return add_note(title, body, parent_id=None)
    parent = anchor.get("parent_id")
    pid = None if parent in (None, "") else str(parent)
    sibs = children_of(pid)
    idx = next((i for i, s in enumerate(sibs) if str(s.get("id")) == str(after_id)), len(sibs) - 1)
    entry = add_note(title, body, parent_id=pid)
    # add_note 已追加到末尾；重排到 anchor 之后
    sibs = [s for s in children_of(pid) if str(s.get("id")) != str(entry["id"])]
    insert_at = min(idx + 1, len(sibs))
    sibs.insert(insert_at, entry)
    for i, s in enumerate(sibs):
        s["order"] = i
    save_nodes(load_nodes())
    return entry


def _settings_path() -> Path:
    return module_data_dir("quick_notepad", create=True) / "settings.json"


def load_settings() -> dict[str, Any]:
    path = _settings_path()
    defaults = {"editor_mode": "rich", "view_mode": "edit"}
    if not path.is_file():
        return dict(defaults)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            mode = str(raw.get("editor_mode") or "rich")
            if mode not in ("simple", "rich"):
                mode = "rich"
            view = str(raw.get("view_mode") or "edit")
            if view not in ("edit", "design", "preview"):
                view = "edit"
            return {"editor_mode": mode, "view_mode": view}
    except Exception:
        pass
    return dict(defaults)


def save_settings(settings: dict[str, Any]) -> None:
    cur = load_settings()
    mode = str(settings.get("editor_mode", cur.get("editor_mode")) or "rich")
    if mode not in ("simple", "rich"):
        mode = "rich"
    view = str(settings.get("view_mode", cur.get("view_mode")) or "edit")
    if view not in ("edit", "design", "preview"):
        view = "edit"
    _settings_path().write_text(
        json.dumps({"editor_mode": mode, "view_mode": view}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
