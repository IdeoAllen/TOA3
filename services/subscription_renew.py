# -*- coding: utf-8 -*-
"""到期续费：推断 pack、一键下单支付激活。"""
from __future__ import annotations

from typing import Any, Tuple

_DEFAULT_PACK = "starter"
_ALL_PACK = "professional"


def is_activation_block(reason: str) -> bool:
    """单机/未授权/需激活 — 应引导激活，而非续费。"""
    text = str(reason or "")
    keys = (
        "完整版",
        "未授权",
        "授权码",
        "激活",
        "单机基础",
        "单机体验",
        "local_free",
    )
    return any(k in text for k in keys)


def is_renewable_block(reason: str) -> bool:
    """已付费授权到期/续订 — 才弹续费窗。"""
    text = str(reason or "")
    if is_activation_block(text):
        return False
    keys = ("到期", "续费", "订阅", "expired", "已过期")
    return any(k in text for k in keys)


def should_prompt_renew_dialog(*, reason: str | None = None) -> bool:
    """启动/导航时是否应提供续费（排除单机与从未激活）。"""
    from services.license_manager import global_license_manager

    lm = global_license_manager
    if lm.is_standalone_mode() or lm.is_licensed():
        return False
    text = str(reason if reason is not None else lm.get_validity_text() or "")
    return is_renewable_block(text)


def _sellable_pack_ids() -> set[str]:
    from services.feature_packs import list_packs

    return {str(p.get("id") or "") for p in list_packs(sellable_only=True) if p.get("id")}


def infer_renew_pack_id(info: dict[str, Any] | None = None) -> str:
    """从上次授权推断续费 pack。"""
    from services.license_manager import global_license_manager

    data = info if isinstance(info, dict) else global_license_manager.get_license_info()
    sellable = _sellable_pack_ids()
    plan = str(data.get("plan_id") or "").strip()
    if plan and plan in sellable:
        return plan

    feats = data.get("features") or []
    if isinstance(feats, list):
        if "all" in feats:
            return _ALL_PACK if _ALL_PACK in sellable else _DEFAULT_PACK
        for f in feats:
            fid = str(f or "").strip()
            if fid in sellable:
                return fid

    for u in data.get("authorized_users") or []:
        if not isinstance(u, dict):
            continue
        for f in u.get("features") or u.get("menus") or []:
            fid = str(f or "").strip()
            if fid in sellable:
                return fid
    return _DEFAULT_PACK


def renew_profile(info: dict[str, Any] | None = None) -> dict[str, str]:
    from services.license_manager import global_license_manager

    data = info if isinstance(info, dict) else global_license_manager.get_license_info()
    name = str(data.get("user_name") or "").strip()
    phone = str(data.get("phone") or "").strip()
    if not phone:
        for u in data.get("authorized_users") or []:
            if not isinstance(u, dict):
                continue
            if str(u.get("name") or "").strip() == name or not name:
                phone = str(u.get("phone") or "").strip()
                if not name:
                    name = str(u.get("name") or "").strip()
            if phone:
                break
    pack_id = infer_renew_pack_id(data)
    from services.feature_packs import list_packs

    pack_name = pack_id
    for p in list_packs(sellable_only=True):
        if p.get("id") == pack_id:
            pack_name = str(p.get("name") or pack_id)
            break
    return {
        "name": name,
        "phone": phone,
        "pack_id": pack_id,
        "pack_name": pack_name,
    }


def fetch_renew_quote(pack_id: str) -> Tuple[bool, dict, str]:
    from services.commerce_client import list_sellable_packs

    ok, packs, commerce, err = list_sellable_packs()
    if not ok:
        return False, {}, err
    row = next((p for p in packs if str(p.get("id") or "") == pack_id), None)
    if not row:
        return False, {}, f"未找到功能包 {pack_id}"
    days = int(commerce.get("default_license_days") or 365)
    try:
        days = int(row.get("default_days") or days)
    except Exception:
        pass
    return True, {
        "pack_id": pack_id,
        "pack_name": str(row.get("name") or pack_id),
        "price_yuan": int(row.get("price_yuan") or 0),
        "license_days": days,
        "mock_pay": bool((commerce.get("mock_payment") or {}).get("enabled", True)),
    }, ""


def renew_one_click(
    *,
    name: str,
    phone: str,
    pack_id: str | None = None,
) -> Tuple[bool, str]:
    """创建订单 → 模拟/终端支付 → 激活。成功返回新的有效期文案。"""
    from services.upgrade_flow import purchase_one_click

    pid = str(pack_id or infer_renew_pack_id()).strip() or _DEFAULT_PACK
    return purchase_one_click(pack_id=pid, name=name, phone=phone)
