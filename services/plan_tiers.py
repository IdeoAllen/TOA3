# -*- coding: utf-8 -*-
"""产品方案等级：用于低套餐提示升级。"""
from __future__ import annotations

from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def _tier_map() -> dict[str, int]:
    """plan_id -> tier（价高 tier 高；同价按 id 稳定排序）。"""
    mapping: dict[str, int] = {}
    try:
        from services.commerce_client import list_sellable_packs

        ok, packs, _, _ = list_sellable_packs()
        if not ok:
            return mapping
        rows = sorted(
            [p for p in packs if isinstance(p, dict) and p.get("id")],
            key=lambda p: (int(p.get("price_yuan") or 0), str(p.get("id") or "")),
        )
        for idx, row in enumerate(rows, start=1):
            pid = str(row.get("plan_id") or row.get("id") or "").strip()
            if pid:
                mapping[pid] = idx
    except Exception:
        pass
    return mapping


def plan_tier(plan_id: str) -> int:
    pid = str(plan_id or "").strip()
    if not pid:
        return 0
    if pid in ("all", "enterprise", "professional"):
        return 999
    return _tier_map().get(pid, 0)


def plan_display_name(plan_id: str) -> str:
    pid = str(plan_id or "").strip()
    if not pid:
        return ""
    try:
        from services.feature_packs import list_packs

        for p in list_packs(sellable_only=True):
            if str(p.get("id") or "") == pid:
                return str(p.get("name") or pid)
    except Exception:
        pass
    return pid


def current_plan_id() -> str:
    try:
        from services.license_manager import global_license_manager

        info = global_license_manager.get_license_info()
        pid = str(info.get("plan_id") or "").strip()
        if pid and pid not in ("all", "local_free"):
            return pid
        feats = info.get("features") or []
        if isinstance(feats, list):
            sellable = set(_tier_map().keys())
            for f in feats:
                fid = str(f or "").strip()
                if fid in sellable:
                    return fid
    except Exception:
        pass
    return ""


def is_upgrade_needed(*, target_plan_id: str, current_plan_id: str = "") -> bool:
    cur = str(current_plan_id or "").strip() or current_plan_id_from_session()
    tgt = str(target_plan_id or "").strip()
    if not cur or not tgt:
        return False
    ct = plan_tier(cur)
    tt = plan_tier(tgt)
    if ct <= 0 or tt <= 0:
        return False
    return tt > ct


def current_plan_id_from_session() -> str:
    return current_plan_id()


def suggest_upgrade_plan(*, module_id: str, current_plan_id: str = "") -> str:
    """覆盖 module 的最低可售方案；若当前方案 tier 已够但缺 module，取更高 tier。"""
    from services.upgrade_flow import suggest_pack_for_module

    base = suggest_pack_for_module(module_id)
    cur = str(current_plan_id or current_plan_id_from_session() or "").strip()
    if not cur:
        return base
    if is_upgrade_needed(target_plan_id=base, current_plan_id=cur):
        return base
    bt = plan_tier(base)
    ct = plan_tier(cur)
    if bt > ct:
        return base
    # 当前 tier 不低但 module 未包含 → 找更高 tier 且含 module 的方案
    try:
        from services.commerce_client import list_sellable_packs
        from services.feature_packs import expand_features

        ok, packs, _, _ = list_sellable_packs()
        if not ok:
            return base
        mid = str(module_id or "").strip()
        candidates: list[tuple[int, int, str]] = []
        for row in packs:
            pid = str(row.get("id") or "").strip()
            if not pid:
                continue
            feats = expand_features([pid])
            if mid and mid not in feats and "all" not in feats:
                continue
            tier = plan_tier(pid)
            if tier <= ct:
                continue
            price = int(row.get("price_yuan") or 0)
            candidates.append((tier, price, pid))
        if candidates:
            candidates.sort(key=lambda x: (x[0], x[1], x[2]))
            return candidates[0][2]
    except Exception:
        pass
    return base


def upgrade_hint(*, module_id: str, current_plan_id: str = "") -> str:
    cur = str(current_plan_id or current_plan_id_from_session() or "").strip()
    tgt = suggest_upgrade_plan(module_id=module_id, current_plan_id=cur)
    if not cur:
        return ""
    if not is_upgrade_needed(target_plan_id=tgt, current_plan_id=cur):
        return ""
    cur_name = plan_display_name(cur)
    tgt_name = plan_display_name(tgt)
    return f"当前为「{cur_name}」，升级至「{tgt_name}」即可使用更多功能"
