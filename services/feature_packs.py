# -*- coding: utf-8 -*-
"""功能授权包（SKU）：出售单位 → 展开为菜单 feature 列表。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from services.config_service import project_root


@lru_cache(maxsize=1)
def _load_raw() -> dict[str, Any]:
    path = project_root() / "config" / "feature_packs.yml"
    if not path.is_file():
        return {"packs": {}}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {"packs": {}}


def reload_packs() -> None:
    _load_raw.cache_clear()


def list_packs(*, sellable_only: bool = False) -> list[dict[str, Any]]:
    packs = _load_raw().get("packs") or {}
    out: list[dict[str, Any]] = []
    for pid, block in packs.items():
        if not isinstance(block, dict):
            continue
        if sellable_only and not block.get("sellable", True):
            continue
        out.append(
            {
                "id": pid,
                "name": str(block.get("name") or pid),
                "desc": str(block.get("desc") or ""),
                "sellable": bool(block.get("sellable", True)),
            }
        )
    return out


def expand_features(tokens: list[str] | None, *, _stack: frozenset[str] | None = None) -> list[str]:
    """把 pack_id / menu_id / all 展开为扁平 menu feature 列表。"""
    if not tokens:
        return []
    stack = set(_stack or ())
    packs = _load_raw().get("packs") or {}
    result: set[str] = set()
    for raw in tokens:
        token = str(raw or "").strip()
        if not token:
            continue
        if token == "all":
            return ["all"]
        if token in stack:
            continue
        block = packs.get(token)
        if isinstance(block, dict):
            nested = list(block.get("features") or [])
            for inc in block.get("includes") or []:
                nested.append(str(inc))
            result.update(expand_features(nested, _stack=frozenset(stack | {token})))
        else:
            result.add(token)
    if "all" in result:
        return ["all"]
    return sorted(result)


def pack_summary_lines() -> list[str]:
    lines: list[str] = []
    for p in list_packs(sellable_only=True):
        feats = expand_features([p["id"]])
        n = "全部" if feats == ["all"] else str(len(feats))
        lines.append(f"{p['id']}\t{p['name']}\t功能数={n}\t{p.get('desc') or ''}")
    return lines
