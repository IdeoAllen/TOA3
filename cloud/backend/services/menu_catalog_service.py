# -*- coding: utf-8 -*-
"""TOA3 菜单目录（只读）— 校验 feature_packs 引用的 module_id。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from services import pack_service as packs

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


@lru_cache(maxsize=1)
def _load_catalog_raw() -> dict[str, Any]:
    path = CONFIG_DIR / "menu_catalog.yml"
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def reload_catalog() -> None:
    _load_catalog_raw.cache_clear()


def catalog_meta() -> dict[str, Any]:
    raw = _load_catalog_raw()
    modules = raw.get("modules") or []
    return {
        "product": str(raw.get("product") or "TOA3"),
        "app_version": str(raw.get("app_version") or ""),
        "exported_at": str(raw.get("exported_at") or ""),
        "module_count": len(modules) if isinstance(modules, list) else 0,
        "synced": bool(raw.get("modules")),
    }


def module_index() -> dict[str, dict[str, Any]]:
    raw = _load_catalog_raw()
    modules = raw.get("modules") or []
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(modules, list):
        return out
    for row in modules:
        if isinstance(row, dict):
            mid = str(row.get("id") or "").strip()
            if mid:
                out[mid] = row
    return out


def special_ids() -> frozenset[str]:
    raw = _load_catalog_raw()
    spec = raw.get("special_ids") or []
    base = frozenset(str(x).strip() for x in spec if str(x).strip())
    return base | frozenset(module_index().keys())


def validate_feature_tokens(tokens: list[str] | None) -> dict[str, Any]:
    """校验展开后的 feature / module_id 列表。"""
    expanded = packs.expand_features(tokens)
    idx = module_index()
    known_special = special_ids()

    modules: list[dict[str, Any]] = []
    unknown: list[str] = []
    if expanded == ["all"]:
        return {
            "ok": True,
            "scope": "all",
            "modules": [],
            "unknown": [],
            "module_count": -1,
        }

    for token in expanded:
        t = str(token or "").strip()
        if not t:
            continue
        if t in idx:
            row = idx[t]
            modules.append(
                {
                    "id": t,
                    "name": row.get("name") or t,
                    "group": row.get("group") or "",
                    "group_label": row.get("group_label") or "",
                    "show": bool(row.get("show", True)),
                    "requires_license": bool(row.get("requires_license", False)),
                    "migration_status": row.get("migration_status") or "",
                }
            )
        elif t in known_special:
            modules.append({"id": t, "name": t, "group": "", "group_label": "", "special": True})
        else:
            unknown.append(t)

    modules.sort(key=lambda x: x.get("id") or "")
    return {
        "ok": not unknown,
        "scope": "partial",
        "modules": modules,
        "unknown": sorted(set(unknown)),
        "module_count": len(modules),
    }


def enrich_pack(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return row
    validation = validate_feature_tokens(list(row.get("features") or []))
    out = dict(row)
    out["menu_validation"] = validation
    return out
