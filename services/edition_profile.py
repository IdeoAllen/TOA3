# -*- coding: utf-8 -*-
"""发行版/体验版配置：菜单白名单与窗口后缀。"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from services.config_service import load_config, project_root


def edition_id() -> str:
    env = os.environ.get("TOA_EDITION", "").strip()
    if env:
        return env
    cfg = load_config()
    block = cfg.get("edition") or {}
    if isinstance(block, dict):
        return str(block.get("id") or "").strip()
    return ""


@lru_cache(maxsize=4)
def _load_profile_file(relative: str) -> dict[str, Any]:
    path = project_root() / "config" / "editions" / relative
    if not path.is_file():
        path = project_root() / relative
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def active_profile() -> dict[str, Any]:
    eid = edition_id()
    if not eid:
        return {}
    cfg = load_config()
    block = cfg.get("edition") or {}
    rel = ""
    if isinstance(block, dict):
        rel = str(block.get("profile") or "").strip()
    if rel:
        prof = _load_profile_file(rel)
        if prof:
            return prof
    return _load_profile_file(f"{eid}.yml")


def window_title_suffix() -> str:
    prof = active_profile()
    return str(prof.get("window_title_suffix") or "").strip()


def edition_label() -> str:
    prof = active_profile()
    return str(prof.get("label") or edition_id() or "").strip()


def menu_whitelist() -> frozenset[str]:
    prof = active_profile()
    raw = prof.get("menu_whitelist") or []
    if not isinstance(raw, list):
        return frozenset()
    return frozenset(str(x).strip() for x in raw if str(x).strip())


def experimental_menu_ids() -> frozenset[str]:
    prof = active_profile()
    raw = prof.get("experimental_menu_ids") or []
    if not isinstance(raw, list):
        return frozenset()
    return frozenset(str(x).strip() for x in raw if str(x).strip())


def nav_menu_ids() -> frozenset[str]:
    """侧栏可见 = 承诺白名单 + 实验模块（体验版）。"""
    wl = menu_whitelist()
    if not wl:
        return frozenset()
    return wl | experimental_menu_ids()


def should_hide_non_whitelist() -> bool:
    prof = active_profile()
    return bool(prof.get("hide_non_whitelist", False))


def filter_menu_by_edition(items: list[dict]) -> list[dict]:
    """按体验版/发行版白名单裁剪侧栏（不影响 access_control 授权逻辑）。"""
    try:
        from services.license_manager import global_license_manager

        if global_license_manager.is_admin_user():
            return items
    except Exception:
        pass
    if not edition_id():
        return items
    wl = menu_whitelist()
    if not wl:
        return items
    if not should_hide_non_whitelist():
        return items
    allowed = nav_menu_ids()
    out: list[dict] = []
    for item in items:
        mid = str(item.get("id") or "").strip()
        if mid in allowed:
            out.append(item)
    return out


def reload_edition_profile() -> None:
    _load_profile_file.cache_clear()
