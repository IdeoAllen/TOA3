# -*- coding: utf-8 -*-
"""迁移清单：空页面 / MVP / 已完成 / 缺失 状态与缺口说明。

绿灯（done）铁律：gaps 非空则强制降为 mvp，防止误标完成。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from services.config_service import project_root

Status = str  # done | mvp | stub | missing
_VALID = frozenset({"done", "mvp", "stub", "missing"})


def reload_manifest() -> dict[str, Any]:
    """测试或热更新时清缓存。"""
    load_manifest.cache_clear()
    return load_manifest()


@lru_cache(maxsize=1)
def load_manifest() -> dict[str, Any]:
    path = project_root() / "config" / "migration_manifest.yml"
    if not path.is_file():
        return {}
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return dict(doc.get("modules") or {})
    except Exception:
        return {}


def get_module_meta(module_id: str) -> dict[str, Any]:
    return dict(load_manifest().get(str(module_id or "").strip()) or {})


def module_gaps(module_id: str) -> list[str]:
    meta = get_module_meta(module_id)
    gaps = meta.get("gaps") or []
    return [str(g) for g in gaps if str(g).strip()]


def get_module_status(module_id: str) -> Status:
    """首页指示灯用状态。有 gaps 的 done 一律降为 mvp。"""
    meta = get_module_meta(module_id)
    if not meta:
        # 未进清单但已挂菜单：按迁移中处理，避免误绿灯
        return "mvp"
    status = str(meta.get("status") or "mvp").strip().lower()
    if status not in _VALID:
        status = "mvp"
    if status == "done" and module_gaps(module_id):
        return "mvp"
    return status


def is_stub(module_id: str) -> bool:
    return get_module_status(module_id) == "stub"


def is_mvp(module_id: str) -> bool:
    return get_module_status(module_id) == "mvp"


def is_done(module_id: str) -> bool:
    return get_module_status(module_id) == "done"


def modules_by_status(status: Status) -> list[str]:
    out: list[str] = []
    for mid in load_manifest():
        if get_module_status(mid) == status:
            out.append(mid)
    return sorted(out)


def implementation_order() -> list[str]:
    """按 priority P0 优先、stub/mvp/missing 待办排序。"""
    manifest = load_manifest()
    scored: list[tuple[int, int, str]] = []
    for mid, meta in manifest.items():
        if mid in ("home", "__about__", "theme_preview", "system_settings"):
            continue
        status = get_module_status(mid)
        if status == "done":
            continue
        pri = 0 if str(meta.get("priority") or "").upper() == "P0" else 1
        status_rank = {"missing": 0, "stub": 1, "mvp": 2}.get(status, 3)
        scored.append((pri, status_rank, mid))
    scored.sort(key=lambda t: (t[0], t[1], t[2]))
    return [mid for _, _, mid in scored]


def status_label(module_id: str) -> str:
    st = get_module_status(module_id)
    return {
        "done": "已完成",
        "mvp": "进行中（未做强）",
        "stub": "待开发（空页面）",
        "missing": "尚未建模块",
    }.get(st, "进行中（未做强）")


def audit_false_done() -> list[str]:
    """清单里写 done 但带 gaps 的模块（运行时已降为 mvp）。"""
    bad: list[str] = []
    for mid, meta in load_manifest().items():
        if str(meta.get("status") or "").lower() != "done":
            continue
        if module_gaps(mid):
            bad.append(mid)
    return sorted(bad)
