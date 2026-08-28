# -*- coding: utf-8 -*-
"""产品方案目录（运营台维护；pack_id 为兼容别名 = plan_id）。"""
from __future__ import annotations

from typing import Any, Tuple


def as_product_plan(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row or {})
    pid = str(item.get("plan_id") or item.get("id") or item.get("pack_id") or "").strip()
    if pid:
        item["plan_id"] = pid
        item["pack_id"] = pid
        item["id"] = pid
    name = str(item.get("plan_name") or item.get("name") or pid)
    item["plan_name"] = name
    item["name"] = name
    try:
        days = max(1, int(item.get("validity_days") or item.get("license_days") or 365))
    except Exception:
        days = 365
    item["validity_days"] = days
    return item


def list_sellable_plans() -> Tuple[bool, list[dict[str, Any]], dict, str]:
    from services.commerce_client import list_sellable_packs

    ok, rows, commerce, err = list_sellable_packs()
    if not ok:
        return False, [], commerce, err
    plans = [as_product_plan(r) for r in rows if isinstance(r, dict)]
    return True, plans, commerce, ""


def resolve_plan_id(*, plan_id: str = "", pack_id: str = "") -> str:
    return str(plan_id or pack_id or "").strip()
