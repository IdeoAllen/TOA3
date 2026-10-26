# -*- coding: utf-8 -*-
"""功能包（SKU）目录 — 与 TOA3 config/feature_packs.yml 同源。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


@lru_cache(maxsize=1)
def _load_packs_raw() -> dict[str, Any]:
    path = CONFIG_DIR / "feature_packs.yml"
    if not path.is_file():
        return {"packs": {}}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {"packs": {}}


@lru_cache(maxsize=1)
def _load_commerce() -> dict[str, Any]:
    path = CONFIG_DIR / "commerce.yml"
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def reload_catalog() -> None:
    _load_packs_raw.cache_clear()
    _load_commerce.cache_clear()


def default_license_days() -> int:
    try:
        return max(1, int(_load_commerce().get("default_license_days") or 365))
    except Exception:
        return 365


def pack_price_yuan(pack_id: str) -> int:
    prices = _load_commerce().get("pack_prices_yuan") or {}
    try:
        return max(0, int(prices.get(pack_id) or 0))
    except Exception:
        return 0


def expand_features(tokens: list[str] | None, *, _stack: frozenset[str] | None = None) -> list[str]:
    if not tokens:
        return []
    stack = set(_stack or ())
    packs = _load_packs_raw().get("packs") or {}
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


def get_pack(pack_id: str, db=None) -> dict[str, Any] | None:
    pid = str(pack_id or "").strip()
    if not pid:
        return None
    if db is not None:
        from services import product_catalog_service as cat

        row = cat.get_pack_db(db, pid)
        if row:
            return row
    block = (_load_packs_raw().get("packs") or {}).get(pid)
    if not isinstance(block, dict):
        return None
    feats = expand_features([pid])
    try:
        validity_days = max(1, int(block.get("validity_days") or default_license_days()))
    except Exception:
        validity_days = default_license_days()
    return {
        "id": pid,
        "plan_id": pid,
        "name": str(block.get("name") or pid),
        "plan_name": str(block.get("name") or pid),
        "desc": str(block.get("desc") or ""),
        "sellable": bool(block.get("sellable", True)),
        "features": feats,
        "feature_count": len(feats) if feats != ["all"] else -1,
        "price_yuan": pack_price_yuan(pid),
        "validity_days": validity_days,
        "includes": list(block.get("includes") or []),
        "pack_id": pid,
    }


def list_packs(*, sellable_only: bool = False, include_free: bool = True) -> list[dict[str, Any]]:
    packs = _load_packs_raw().get("packs") or {}
    out: list[dict[str, Any]] = []
    for pid, block in packs.items():
        if not isinstance(block, dict):
            continue
        sellable = bool(block.get("sellable", True))
        if sellable_only and not sellable:
            continue
        if not include_free and pid == "local_free":
            continue
        item = get_pack(pid)
        if item:
            out.append(item)
    out.sort(key=lambda x: (not x.get("sellable"), x.get("id") or ""))
    return out


def pack_menus_for_license(pack_id: str, db=None) -> list[str]:
    """写入授权码 / menus_json：存 pack_id，TOA3 端会展开。"""
    pid = str(pack_id or "").strip()
    if not pid:
        return ["all"]
    if pid == "all":
        return ["all"]
    pack = get_pack(pid, db=db)
    if not pack:
        raise ValueError(f"未知功能包：{pid}")
    if not pack.get("sellable", True) and pid not in ("local_free", "experience_beta"):
        raise ValueError(f"功能包不可售：{pid}")
    validation = pack.get("menu_validation") or {}
    if validation and not validation.get("ok", True):
        unknown = validation.get("unknown") or []
        raise ValueError(f"功能包含未发布 module：{', '.join(unknown)}")
    return [pid]


def commerce_summary() -> dict[str, Any]:
    comm = _load_commerce()
    mock = comm.get("mock_payment") or {}
    webhook = comm.get("webhook") or {}
    real = comm.get("real_payment") or {}
    return {
        "default_license_days": default_license_days(),
        "mock_payment_enabled": bool(mock.get("enabled", True)),
        "mock_payment_note": str(mock.get("note") or ""),
        "mock_payment": {
            "enabled": bool(mock.get("enabled", True)),
            "channel": str(mock.get("channel") or "mock"),
            "note": str(mock.get("note") or ""),
        },
        "real_payment_enabled": bool(real.get("enabled", False)),
        "webhook": {
            "configured": bool(webhook.get("secret") or ""),
            "allowed_channels": list(webhook.get("allowed_channels") or ["mock", "wechat", "alipay"]),
        },
    }


def mock_payment_enabled() -> bool:
    mock = _load_commerce().get("mock_payment") or {}
    real = _load_commerce().get("real_payment") or {}
    if bool(real.get("enabled", False)):
        return False
    return bool(mock.get("enabled", True))


def webhook_secret() -> str:
    import os

    from config import WEBHOOK_SECRET

    if WEBHOOK_SECRET:
        return WEBHOOK_SECRET.strip()
    wh = _load_commerce().get("webhook") or {}
    return str(wh.get("secret") or "").strip()


def webhook_allowed_channels() -> frozenset[str]:
    wh = _load_commerce().get("webhook") or {}
    raw = wh.get("allowed_channels") or ["mock", "wechat", "alipay"]
    return frozenset(str(x).strip().lower() for x in raw if str(x).strip())
